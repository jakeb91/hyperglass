"""Import configuration files and returns default values if undefined."""

# Standard Library
import os
import json
from typing import Dict, List, Generator
from pathlib import Path

# Third Party
import yaml
from pydantic import ValidationError

# Project
from hyperglass.log import (
    log,
    set_log_level,
    enable_file_logging,
    enable_syslog_logging,
)
from hyperglass.util import set_app_path, set_cache_env, current_log_level
from hyperglass.defaults import CREDIT
from hyperglass.constants import PARSED_RESPONSE_FIELDS, __version__
from hyperglass.util.files import check_path
from hyperglass.exceptions.private import ConfigError, ConfigMissing
from hyperglass.models.config.params import Params
from hyperglass.models.config.devices import Devices
from hyperglass.models.commands.generic import Directive

# Local
from .markdown import get_markdown
from .validation import validate_config

set_app_path(required=True)

CONFIG_PATH = Path(os.environ["hyperglass_directory"])
log.info("Configuration directory: {d}", d=str(CONFIG_PATH))

# Project Directories
WORKING_DIR = Path(__file__).resolve().parent
CONFIG_FILES = (
    ("hyperglass.yaml", False),
    ("devices.yaml", True),
    ("commands.yaml", False),
)


def _check_config_files(directory: Path):
    """Verify config files exist and are readable."""

    files = ()

    for file in CONFIG_FILES:
        file_name, required = file
        file_path = directory / file_name

        checked = check_path(file_path)

        if checked is None and required:
            raise ConfigMissing(missing_item=str(file_path))

        if checked is None and not required:
            log.warning(
                "'{f}' was not found, but is not required to run hyperglass. "
                + "Defaults will be used.",
                f=str(file_path),
            )
        files += (checked,)

    return files


STATIC_PATH = CONFIG_PATH / "static"

CONFIG_MAIN, CONFIG_DEVICES, CONFIG_COMMANDS = _check_config_files(CONFIG_PATH)


def _config_required(config_path: Path) -> Dict:
    try:
        with config_path.open("r") as cf:
            config = yaml.safe_load(cf)

    except (yaml.YAMLError, yaml.MarkedYAMLError) as yaml_error:
        raise ConfigError(message="Error reading YAML file: '{e}'", e=yaml_error)

    if config is None:
        raise ConfigMissing(missing_item=config_path.name)

    return config


def _config_optional(config_path: Path) -> Dict:

    config = {}

    if config_path is None:
        return config

    else:
        try:
            with config_path.open("r") as cf:
                config = yaml.safe_load(cf) or {}

        except (yaml.YAMLError, yaml.MarkedYAMLError) as yaml_error:
            raise ConfigError(message="Error reading YAML file: '{e}'", e=yaml_error)

    return config


def _get_commands(data: Dict) -> List[Directive]:
    commands = []
    for name, command in data.items():
        try:
            commands.append(Directive(id=name, **command))
        except ValidationError as err:
            raise ConfigError(
                message="Validation error in command '{c}': '{e}'", c=name, e=err
            ) from err
    return commands


def _device_commands(
    device: Dict, directives: List[Directive]
) -> Generator[Directive, None, None]:
    device_commands = device.get("commands", [])
    for directive in directives:
        if directive.id in device_commands:
            yield directive


def _get_devices(data: List[Dict], directives: List[Directive]) -> Devices:
    for device in data:
        device_commands = list(_device_commands(device, directives))
        device["commands"] = device_commands
    return Devices(data)


user_config = _config_optional(CONFIG_MAIN)

# Read raw debug value from config to enable debugging quickly.
set_log_level(logger=log, debug=user_config.get("debug", True))

# Map imported user configuration to expected schema.
log.debug("Unvalidated configuration from {}: {}", CONFIG_MAIN, user_config)
params: Params = validate_config(config=user_config, importer=Params)

# Re-evaluate debug state after config is validated
log_level = current_log_level(log)

if params.debug and log_level != "debug":
    set_log_level(logger=log, debug=True)
elif not params.debug and log_level == "debug":
    set_log_level(logger=log, debug=False)

# Map imported user commands to expected schema.
_user_commands = _config_optional(CONFIG_COMMANDS)
log.debug("Unvalidated commands from {}: {}", CONFIG_COMMANDS, _user_commands)
commands = _get_commands(_user_commands)

# Map imported user devices to expected schema.
_user_devices = _config_required(CONFIG_DEVICES)
log.debug("Unvalidated devices from {}: {}", CONFIG_DEVICES, _user_devices)
devices: Devices = _get_devices(_user_devices.get("routers", []), commands)

# Set cache configurations to environment variables, so they can be
# used without importing this module (Gunicorn, etc).
set_cache_env(db=params.cache.database, host=params.cache.host, port=params.cache.port)

# Set up file logging once configuration parameters are initialized.
enable_file_logging(
    logger=log,
    log_directory=params.logging.directory,
    log_format=params.logging.format,
    log_max_size=params.logging.max_size,
)

# Set up syslog logging if enabled.
if params.logging.syslog is not None and params.logging.syslog.enable:
    enable_syslog_logging(
        logger=log,
        syslog_host=params.logging.syslog.host,
        syslog_port=params.logging.syslog.port,
    )

if params.logging.http is not None and params.logging.http.enable:
    log.debug("HTTP logging is enabled")

# Perform post-config initialization string formatting or other
# functions that require access to other config levels. E.g.,
# something in 'params.web.text' needs to be formatted with a value
# from params.
try:
    params.web.text.subtitle = params.web.text.subtitle.format(
        **params.dict(exclude={"web", "queries", "messages"})
    )

    # If keywords are unmodified (default), add the org name &
    # site_title.
    if Params().site_keywords == params.site_keywords:
        params.site_keywords = sorted(
            {*params.site_keywords, params.org_name, params.site_title}
        )

except KeyError:
    pass


def _build_networks() -> List[Dict]:
    """Build filtered JSON Structure of networks & devices for Jinja templates."""
    networks = []
    _networks = list(set({device.network.display_name for device in devices.objects}))

    for _network in _networks:
        network_def = {"display_name": _network, "locations": []}
        for device in devices.objects:
            if device.network.display_name == _network:
                network_def["locations"].append(
                    {
                        "_id": device._id,
                        "name": device.name,
                        "network": device.network.display_name,
                        "directives": [c.frontend(params) for c in device.commands],
                    }
                )
        networks.append(network_def)

    if not networks:
        raise ConfigError(message="Unable to build network to device mapping")
    return networks


content_params = json.loads(
    params.json(include={"primary_asn", "org_name", "site_title", "site_description"})
)


content_greeting = get_markdown(
    config_path=params.web.greeting,
    default="",
    params={"title": params.web.greeting.title},
)


content_credit = CREDIT.format(version=__version__)

networks = _build_networks()

_include_fields = {
    "cache": {"show_text", "timeout"},
    "debug": ...,
    "developer_mode": ...,
    "primary_asn": ...,
    "request_timeout": ...,
    "org_name": ...,
    "google_analytics": ...,
    "site_title": ...,
    "site_description": ...,
    "site_keywords": ...,
    "web": ...,
    "messages": ...,
}
_frontend_params = params.dict(include=_include_fields)


_frontend_params["web"]["logo"]["light_format"] = params.web.logo.light.suffix
_frontend_params["web"]["logo"]["dark_format"] = params.web.logo.dark.suffix

_frontend_params.update(
    {
        "hyperglass_version": __version__,
        "queries": {**params.queries.map, "list": params.queries.list},
        "networks": networks,
        "parsed_data_fields": PARSED_RESPONSE_FIELDS,
        "content": {"credit": content_credit, "greeting": content_greeting},
    }
)
frontend_params = _frontend_params

URL_DEV = f"http://localhost:{str(params.listen_port)}/"
URL_PROD = "/api/"

REDIS_CONFIG = {
    "host": str(params.cache.host),
    "port": params.cache.port,
    "decode_responses": True,
    "password": params.cache.password,
}
