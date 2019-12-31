#!/usr/bin/env python3

# Standard Library Imports
# Standard Imports
import asyncio
import glob
import grp
import json
import os
import pwd
import random
import shutil
import string
import sys
from functools import update_wrapper
from pathlib import Path

# Third Party Imports
# Module Imports
import click
import requests
import stackprinter
from passlib.hash import pbkdf2_sha256

stackprinter.set_excepthook(style="darkbg2")

# Initialize shutil copy function
cp = shutil.copyfile

# Define working directory
working_directory = os.path.dirname(os.path.abspath(__file__))

# Helpers
NL = "\n"
WS1 = " "
WS2 = "  "
WS4 = "    "
WS6 = "      "
WS8 = "        "
CL = ":"
E_ROCKET = "\U0001F680"
E_SPARKLES = "\U00002728"


def async_command(func):
    func = asyncio.coroutine(func)

    def wrapper(*args, **kwargs):
        loop = asyncio.get_event_loop()
        return loop.run_until_complete(func(*args, **kwargs))

    return update_wrapper(wrapper, func)


def construct_test(test_query, location, test_target):
    """Constructs JSON POST data for test_hyperglass function"""
    constructed_query = json.dumps(
        {"type": test_query, "location": location, "target": test_target}
    )
    return constructed_query


@click.group()
def hg():
    pass


@hg.command("pylint-check", help="Runs Pylint and generates a badge for GitHub")
@click.option(
    "-m", "--number", "num_only", is_flag=True, help="Output Pylint score as integer"
)
@click.option("-b", "--badge", "create_badge", is_flag=True, help="Create Pylint badge")
@click.option(
    "-e", "--print-errors", "errors", is_flag=True, help="Print pylint errors"
)
def pylint_check(num_only, create_badge, errors):
    try:
        import re
        import anybadge
        from pylint import epylint

        pylint_ver = epylint.py_run("hyperglass --version", return_std=True)[
            0
        ].getvalue()
        click.echo("Current directory: " + str(Path.cwd().resolve()))
        click.echo("Pylint Version: " + pylint_ver)
        pylint_stdout, pylint_stderr = epylint.py_run(
            "hyperglass --verbose --rcfile=.pylintrc", return_std=True
        )
        pylint_output = pylint_stdout.getvalue()
        pylint_error = pylint_stderr.getvalue()
        pylint_score = re.search(
            r"Your code has been rated at (\d+\.\d+)\/10.*", pylint_output
        ).group(1)
        if num_only:
            click.echo(pylint_score)
        if errors:
            click.echo(pylint_error)
            click.echo(pylint_output)
        if not pylint_score == "10.00":
            raise RuntimeError(f"Pylint score {pylint_score} not acceptable.")
        if create_badge:
            badge_file = os.path.join(working_directory, "pylint.svg")
            if os.path.exists(badge_file):
                os.remove(badge_file)
            ab_thresholds = {1: "red", 10: "green"}
            badge = anybadge.Badge("pylint", pylint_score, thresholds=ab_thresholds)
            badge.write_badge("pylint.svg")
            click.echo(
                click.style("Created Pylint badge for score: ", fg="white")
                + click.style(pylint_score, fg="blue", bold=True)
            )
    except ImportError as error_exception:
        click.secho(f"Import error:\n{error_exception}", fg="red", bold=True)


@hg.command("pre-check", help="Check hyperglass config & readiness")
def pre_check():
    if sys.version_info < (3, 6):
        click.secho(
            f"Hyperglass requires Python 3.6 or higher. Curren version: Python {sys.version.split()[0]}",
            fg="red",
            bold=True,
        )
    if sys.version_info >= (3, 6):
        click.secho(
            f"✓ Python Version Check passed (Current version: Python {sys.version.split()[0]})",
            fg="green",
            bold=True,
        )
    try:
        from hyperglass import configuration

        config = configuration.params()
        status = True
        while status:
            if config["general"]["primary_asn"] == "65000" or "":
                status = False
                reason = f'Primary ASN is not defined (Current: "{config["general"]["primary_asn"]}")'
                remediation = f"""
To define the Primary ASN paramter, modify your `configuration.toml` and add the following \
configuration:\n
[general]
primary_asn = "<Your Primary AS Number>"
\nIf you do not define a Primary ASN, \"{config["general"]["primary_asn"]}\" will be used."""
                break
                click.secho(reason, fg="red", bold=True)
                click.secho(remediation, fg="blue")
            if config["general"]["org_name"] == "The Company" or "":
                status = False
                reason = f'Org Name is not defined (Current: "{config["general"]["org_name"]}")'
                remediation = f"""
To define an Org Name paramter, modify your `configuration.toml` and add the following \
configuration:\n
[general]
org_name = "<Your Org Name>"
\nIf you do not define an Org Name, \"{config["general"]["org_name"]}\" will be displayed."""
                break
                click.secho(reason, fg="red", bold=True)
                click.secho(remediation, fg="blue")
            click.secho(
                "✓ All critical hyperglass parameters are defined!",
                fg="green",
                bold=True,
            )
            break
    except Exception as e:
        click.secho(f"Exception occurred:\n{e}", fg="red")


@hg.command("test", help="Full test of all backend features")
@click.option("-l", "--location", type=str, required=True, help="Location to query")
@click.option(
    "-4",
    "--target-ipv4",
    "target_ipv4",
    type=str,
    default="1.1.1.0/24",
    required=False,
    show_default=True,
    help="IPv4 Target Address",
)
@click.option(
    "-6",
    "--target-ipv6",
    "target_ipv6",
    type=str,
    default="2606:4700:4700::/48",
    required=False,
    show_default=True,
    help="IPv6 Target Address",
)
@click.option(
    "-c",
    "--community",
    "test_community",
    type=str,
    required=False,
    show_default=True,
    default="65000:1",
    help="BGP Community",
)
@click.option(
    "-a",
    "--aspath",
    "test_aspath",
    type=str,
    required=False,
    show_default=True,
    default="^65001$",
    help="BGP AS Path",
)
@click.option(
    "-r",
    "--requires-ipv6-cidr",
    "requires_ipv6_cidr",
    type=str,
    required=False,
    help="Location for testing IPv6 CIDR requirement",
)
@click.option(
    "-b",
    "--blacklist",
    "test_blacklist",
    type=str,
    default="100.64.0.1",
    required=False,
    show_default=True,
    help="Address to use for blacklist check",
)
@click.option(
    "-h",
    "--host",
    "test_host",
    type=str,
    default="localhost",
    required=False,
    show_default=True,
    help="Name or IP address of hyperglass server",
)
@click.option(
    "-p",
    "--port",
    "test_port",
    type=int,
    default=5000,
    required=False,
    show_default=True,
    help="Port hyperglass is running on",
)
def test_hyperglass(
    location,
    target_ipv4,
    target_ipv6,
    requires_ipv6_cidr,
    test_blacklist,
    test_community,
    test_aspath,
    test_host,
    test_port,
):
    """
    Fully tests hyperglass backend by making use of requests library to
    mimic the JS Ajax POST performed by the front end.
    """
    test_target = None
    invalid_ip = "this_ain't_an_ip!"
    invalid_community = "192.0.2.1"
    invalid_aspath = ".*"
    ipv4_host = "1.1.1.1"
    ipv4_cidr = "1.1.1.0/24"
    ipv6_host = "2606:4700:4700::1111"
    ipv6_cidr = "2606:4700:4700::/48"
    test_headers = {"Content-Type": "application/json"}
    test_endpoint = f"http://{test_host}:{test_port}/lg"
    # No Query Type Test
    try:
        click.secho("Starting No Query Type test...", fg="black")
        test_query = construct_test("", location, target_ipv4)
        hg_response = requests.post(
            test_endpoint, headers=test_headers, data=test_query
        )
        if hg_response.status_code in range(400, 500):
            click.secho("✓ No Query Type test passed", fg="green", bold=True)
        if not hg_response.status_code in range(400, 500):
            click.secho("✗ No Query Type test failed", fg="red", bold=True)
            click.secho(f"Status Code: {hg_response.status_code}", fg="red", bold=True)
            click.secho(hg_response.text, fg="red")
    except Exception as e:
        click.secho(f"Exception occurred:\n{e}")
    # No Location Test
    try:
        click.secho("Starting No Location test...", fg="black")
        test_query = construct_test("bgp_route", "", target_ipv6)
        hg_response = requests.post(
            test_endpoint, headers=test_headers, data=test_query
        )
        if hg_response.status_code in range(400, 500):
            click.secho("✓ No Location test passed", fg="green", bold=True)
        if not hg_response.status_code in range(400, 500):
            click.secho("✗ No Location test failed", fg="red", bold=True)
            click.secho(f"Status Code: {hg_response.status_code}", fg="red", bold=True)
            click.secho(hg_response.text, fg="red")
    except Exception as e:
        click.secho(f"Exception occurred:\n{e}")
    # No Target Test
    try:
        click.secho("Starting No Target test...", fg="black")
        test_query = construct_test("bgp_route", location, "")
        hg_response = requests.post(
            test_endpoint, headers=test_headers, data=test_query
        )
        if hg_response.status_code in range(400, 500):
            click.secho("✓ No Target test passed", fg="green", bold=True)
        if not hg_response.status_code in range(400, 500):
            click.secho("✗ No Target test failed", fg="red", bold=True)
            click.secho(f"Status Code: {hg_response.status_code}", fg="red", bold=True)
            click.secho(hg_response.text, fg="red")
    except Exception as e:
        click.secho(f"Exception occurred:\n{e}")
    # Valid BGP IPv4 Route Test
    try:
        click.secho("Starting Valid BGP IPv4 Route test...", fg="black")
        test_query = construct_test("bgp_route", location, target_ipv4)
        hg_response = requests.post(
            test_endpoint, headers=test_headers, data=test_query
        )
        if hg_response.status_code == 200:
            click.secho("✓ Valid BGP IPv4 Route test passed", fg="green", bold=True)
        if not hg_response.status_code == 200:
            click.secho("✗ Valid BGP IPv4 Route test failed", fg="red", bold=True)
            click.secho(f"Status Code: {hg_response.status_code}", fg="red", bold=True)
            click.secho(hg_response.text, fg="red")
    except Exception as e:
        click.secho(f"Exception occurred:\n{e}")
    # Valid BGP IPv6 Route Test
    try:
        click.secho("Starting Valid BGP IPv6 Route test...", fg="black")
        test_query = construct_test("bgp_route", location, target_ipv6)
        hg_response = requests.post(
            test_endpoint, headers=test_headers, data=test_query
        )
        if hg_response.status_code == 200:
            click.secho("✓ Valid BGP IPv6 Route test passed", fg="green", bold=True)
        if not hg_response.status_code == 200:
            click.secho("✗ Valid BGP IPv6 Route test failed", fg="red", bold=True)
            click.secho(f"Status Code: {hg_response.status_code}", fg="red", bold=True)
            click.secho(hg_response.text, fg="red")
    except Exception as e:
        click.secho(f"Exception occurred:\n{e}")
    # Invalid BGP Route Test
    try:
        click.secho("Starting Invalid BGP IPv4 Route test...", fg="black")
        test_query = construct_test("bgp_route", location, invalid_ip)
        hg_response = requests.post(
            test_endpoint, headers=test_headers, data=test_query
        )
        if hg_response.status_code in range(400, 500):
            click.secho("✓ Invalid BGP IPv4 Route test passed", fg="green", bold=True)
        if not hg_response.status_code in range(400, 500):
            click.secho("✗ Invalid BGP IPv4 Route test failed", fg="red", bold=True)
            click.secho(f"Status Code: {hg_response.status_code}", fg="red", bold=True)
            click.secho(hg_response.text, fg="red")
    except Exception as e:
        click.secho(f"Exception occurred:\n{e}")
    # Requires IPv6 CIDR Test
    if requires_ipv6_cidr:
        try:
            click.secho("Starting Requires IPv6 CIDR test...", fg="black")
            test_query = construct_test("bgp_route", requires_ipv6_cidr, ipv6_host)
            hg_response = requests.post(
                test_endpoint, headers=test_headers, data=test_query
            )
            if hg_response.status_code in range(400, 500):
                click.secho("✓ Requires IPv6 CIDR test passed", fg="green", bold=True)
            if not hg_response.status_code in range(400, 500):
                click.secho("✗ Requires IPv6 CIDR test failed", fg="red", bold=True)
                click.secho(
                    f"Status Code: {hg_response.status_code}", fg="red", bold=True
                )
                click.secho(hg_response.text, fg="red")
        except Exception as e:
            click.secho(f"Exception occurred:\n{e}")
    # Valid BGP Community Test
    try:
        click.secho("Starting Valid BGP Community test...", fg="black")
        test_query = construct_test("bgp_community", location, test_community)
        hg_response = requests.post(
            test_endpoint, headers=test_headers, data=test_query
        )
        if hg_response.status_code == 200:
            click.secho("✓ Valid BGP Community test passed", fg="green", bold=True)
        if not hg_response.status_code == 200:
            click.secho("✗ Valid BGP Community test failed", fg="red", bold=True)
            click.secho(f"Status Code: {hg_response.status_code}", fg="red", bold=True)
            click.secho(hg_response.text, fg="red")
    except Exception as e:
        click.secho(f"Exception occurred:\n{e}")
    # Invalid BGP Community Test
    try:
        click.secho("Starting Invalid BGP Community test...", fg="black")
        test_query = construct_test("bgp_community", location, target_ipv4)
        hg_response = requests.post(
            test_endpoint, headers=test_headers, data=test_query
        )
        if hg_response.status_code in range(400, 500):
            click.secho("✓ Invalid BGP Community test passed", fg="green", bold=True)
        if not hg_response.status_code in range(400, 500):
            click.secho("✗ Invalid BGP Community test failed", fg="red", bold=True)
            click.secho(f"Status Code: {hg_response.status_code}", fg="red", bold=True)
            click.secho(hg_response.text, fg="red")
    except Exception as e:
        click.secho(f"Exception occurred:\n{e}")
    # Valid BGP AS_PATH Test
    try:
        click.secho("Starting Valid BGP AS_PATH test...", fg="black")
        test_query = construct_test("bgp_aspath", location, test_aspath)
        hg_response = requests.post(
            test_endpoint, headers=test_headers, data=test_query
        )
        if hg_response.status_code == 200:
            click.secho("✓ Valid BGP AS_PATH test passed", fg="green", bold=True)
        if not hg_response.status_code == 200:
            click.secho("✗ Valid BGP AS_PATH test failed", fg="red", bold=True)
            click.secho(f"Status Code: {hg_response.status_code}", fg="red", bold=True)
            click.secho(hg_response.text, fg="red")
    except Exception as e:
        click.secho(f"Exception occurred:\n{e}")
    # Invalid BGP AS_PATH Test
    try:
        click.secho("Starting invalid BGP AS_PATH test...", fg="black")
        test_query = construct_test("bgp_aspath", location, invalid_aspath)
        hg_response = requests.post(
            test_endpoint, headers=test_headers, data=test_query
        )
        if hg_response.status_code in range(400, 500):
            click.secho("✓ Invalid BGP AS_PATH test passed", fg="green", bold=True)
        if not hg_response.status_code in range(400, 500):
            click.secho("✗ Invalid BGP AS_PATH test failed", fg="red", bold=True)
            click.secho(f"Status Code: {hg_response.status_code}", fg="red", bold=True)
            click.secho(hg_response.text, fg="red")
    except Exception as e:
        click.secho(f"Exception occurred:\n{e}")
    # Valid IPv4 Ping Test
    try:
        click.secho("Starting Valid IPv4 Ping test...", fg="black")
        test_query = construct_test("ping", location, ipv4_host)
        hg_response = requests.post(
            test_endpoint, headers=test_headers, data=test_query
        )
        if hg_response.status_code == 200:
            click.secho("✓ Valid IPv4 Ping test passed", fg="green", bold=True)
        if not hg_response.status_code == 200:
            click.secho("✗ Valid IPv4 Ping test failed", fg="red", bold=True)
            click.secho(f"Status Code: {hg_response.status_code}", fg="red", bold=True)
            click.secho(hg_response.text, fg="red")
    except Exception as e:
        click.secho(f"Exception occurred:\n{e}")
    # Valid IPv6 Ping Test
    try:
        click.secho("Starting Valid IPv6 Ping test...", fg="black")
        test_query = construct_test("ping", location, ipv6_host)
        hg_response = requests.post(
            test_endpoint, headers=test_headers, data=test_query
        )
        if hg_response.status_code == 200:
            click.secho("✓ Valid IPv6 Ping test passed", fg="green", bold=True)
        if not hg_response.status_code == 200:
            click.secho("✗ Valid IPv6 Ping test failed", fg="red", bold=True)
            click.secho(f"Status Code: {hg_response.status_code}", fg="red", bold=True)
            click.secho(hg_response.text, fg="red")
    except Exception as e:
        click.secho(f"Exception occurred:\n{e}")
    # Invalid IPv4 Ping Test
    try:
        click.secho("Starting Invalid IPv4 Ping test...", fg="black")
        test_query = construct_test("ping", location, ipv4_cidr)
        hg_response = requests.post(
            test_endpoint, headers=test_headers, data=test_query
        )
        if hg_response.status_code in range(400, 500):
            click.secho("✓ Invalid IPv4 Ping test passed", fg="green", bold=True)
        if not hg_response.status_code in range(400, 500):
            click.secho("✗ Invalid IPv4 Ping test failed", fg="red", bold=True)
            click.secho(f"Status Code: {hg_response.status_code}", fg="red", bold=True)
            click.secho(hg_response.text, fg="red")
    except Exception as e:
        click.secho(f"Exception occurred:\n{e}")
    # Invalid IPv6 Ping Test
    try:
        click.secho("Starting Invalid IPv6 Ping test...", fg="black")
        test_query = construct_test("ping", location, ipv6_cidr)
        hg_response = requests.post(
            test_endpoint, headers=test_headers, data=test_query
        )
        if hg_response.status_code in range(400, 500):
            click.secho("✓ Invalid IPv6 Ping test passed", fg="green", bold=True)
        if not hg_response.status_code in range(400, 500):
            click.secho("✗ Invalid IPv6 Ping test failed", fg="red", bold=True)
            click.secho(f"Status Code: {hg_response.status_code}", fg="red", bold=True)
            click.secho(hg_response.text, fg="red")
    except Exception as e:
        click.secho(f"Exception occurred:\n{e}")
    # Blacklist Test
    try:
        click.secho("Starting Blacklist test...", fg="black")
        test_query = construct_test("bgp_route", location, test_blacklist)
        hg_response = requests.post(
            test_endpoint, headers=test_headers, data=test_query
        )
        if hg_response.status_code in range(400, 500):
            click.secho("✓ Blacklist test passed", fg="green", bold=True)
        if not hg_response.status_code in range(400, 500):
            click.secho("✗ Blacklist test failed", fg="red", bold=True)
            click.secho(f"Status Code: {hg_response.status_code}", fg="red", bold=True)
            click.secho(hg_response.text, fg="red")
    except Exception as e:
        click.secho(f"Exception occurred:\n{e}")


@hg.command("clear-cache", help="Clear Flask cache")
@async_command
async def clearcache():
    """Clears the Flask-Caching cache"""
    try:
        import hyperglass.hyperglass

        message = await hyperglass.hyperglass.clear_cache()
        # click.secho("✓ Successfully cleared cache.", fg="green", bold=True)
        click.secho("✓ " + str(message), fg="green", bold=True)
    except (ImportError, RuntimeWarning):
        click.secho("✗ Failed to clear cache.", fg="red", bold=True)
        raise


@hg.command("generate-key", help="Generate API key & hash")
@click.option(
    "-l", "--length", "string_length", type=int, default=16, show_default=True
)
def generatekey(string_length):
    """
    Generates 16 character API Key for hyperglass-frr API, and a
    corresponding PBKDF2 SHA256 Hash.
    """
    ld = string.ascii_letters + string.digits
    nl = "\n"
    api_key = "".join(random.choice(ld) for i in range(string_length))
    key_hash = pbkdf2_sha256.hash(api_key)
    line_len = len(key_hash)
    ak_info = "  Your API Key is: "
    ak_help1 = "  Put this in the"
    ak_help2 = " configuration.yaml "
    ak_help3 = "of your API module."
    kh_info = "  Your Key Hash is: "
    kh_help1 = "  Use this as the password for the corresponding device in"
    kh_help2 = " devices.yaml"
    kh_help3 = "."
    ak_info_len = len(ak_info + api_key)
    ak_help_len = len(ak_help1 + ak_help2 + ak_help3)
    kh_info_len = len(kh_info + key_hash)
    kh_help_len = len(kh_help1 + kh_help2 + kh_help3)
    ak_kh = [ak_info_len, ak_help_len, kh_info_len, kh_help_len]
    ak_kh.sort()
    longest_line = ak_kh[-1] + 2
    s_box = {"fg": "white", "dim": True, "bold": True}
    s_txt = {"fg": "white"}
    s_ak = {"fg": "green", "bold": True}
    s_kh = {"fg": "blue", "bold": True}
    s_file = {"fg": "yellow"}
    click.echo(
        click.style("┌" + ("─" * longest_line) + "┐", **s_box)
        + click.style(nl + "│", **s_box)
        + click.style(ak_info, **s_txt)
        + click.style(api_key, **s_ak)
        + click.style(" " * (longest_line - ak_info_len) + "│", **s_box)
        + click.style(nl + "│", **s_box)
        + click.style(ak_help1, **s_txt)
        + click.style(ak_help2, **s_file)
        + click.style(ak_help3, **s_txt)
        + click.style(" " * (longest_line - ak_help_len) + "│", **s_box)
        + click.style(nl + "├" + ("─" * longest_line) + "┤", **s_box)
        + click.style(nl + "│", **s_box)
        + click.style(kh_info, **s_txt)
        + click.style(key_hash, **s_kh)
        + click.style(" " * (longest_line - kh_info_len) + "│", **s_box)
        + click.style(nl + "│", **s_box)
        + click.style(kh_help1, **s_txt)
        + click.style(kh_help2, **s_file)
        + click.style(kh_help3, **s_txt)
        + click.style(" " * (longest_line - kh_help_len) + "│", **s_box)
        + click.style(nl + "└" + ("─" * longest_line) + "┘", **s_box)
    )


def render_hyperglass_assets():
    """Render theme template to Sass file and build web assets"""
    try:
        from hyperglass.render import render_assets
        from hyperglass.exceptions import HyperglassError
    except ImportError as import_error:
        raise click.ClickException(
            click.style("✗ Error importing hyperglass: ", fg="red", bold=True)
            + click.style(import_error, fg="blue")
        )
    assets_rendered = False
    try:
        render_assets()
        assets_rendered = True
    except HyperglassError as e:
        raise click.ClickException(str(e))
    return assets_rendered


def start_dev_server(host, port):
    """Starts Sanic development server for testing without WSGI/Reverse Proxy"""
    try:
        from hyperglass.hyperglass import app, APP_PARAMS
        from hyperglass.configuration import params
    except ImportError as import_error:
        raise click.ClickException(
            click.style("✗ Error importing hyperglass: ", fg="red", bold=True)
            + click.style(import_error, fg="blue")
        )
    try:
        if host is not None:
            APP_PARAMS["host"] = host
        if port is not None:
            APP_PARAMS["port"] = port

        click.echo(
            click.style(
                NL + f"✓ Starting hyperglass web server on...", fg="green", bold=True
            )
            + NL
            + E_SPARKLES
            + NL
            + E_SPARKLES * 2
            + NL
            + E_SPARKLES * 3
            + NL
            + WS8
            + click.style("http://", fg="white")
            + click.style(str(APP_PARAMS["host"]), fg="blue", bold=True)
            + click.style(CL, fg="white")
            + click.style(str(APP_PARAMS["port"]), fg="magenta", bold=True)
            + NL
            + WS4
            + E_ROCKET
            + NL
            + NL
            + WS1
            + E_ROCKET
            + NL
        )
        app.run(**APP_PARAMS)
    except Exception as e:
        raise click.ClickException(
            click.style("✗ Failed to start test server: ", fg="red", bold=True)
            + click.style(e, fg="red")
        )


@hg.command("dev-server", help="Start development web server")
@click.option("--host", type=str, required=False, help="Listening IP")
@click.option("--port", type=int, required=False, help="TCP Port")
@click.option(
    "--assets/--no-assets", default=False, help="Render Theme & Build Web Assets"
)
def dev_server(host, port, assets):
    """Renders theme and web assets, then starts dev web server"""
    if assets:
        try:
            assets_rendered = render_hyperglass_assets()
        except Exception as e:
            raise click.ClickException(
                click.style("✗ Error rendering assets: ", fg="red", bold=True)
                + click.style(e, fg="blue")
            )
        if assets_rendered:
            start_dev_server(host, port)
    if not assets:
        start_dev_server(host, port)


@hg.command("render-assets", help="Render theme & build web assets")
def render_assets():
    """Render theme template to Sass file and build web assets"""
    assets_rendered = render_hyperglass_assets()
    if not assets_rendered:
        raise click.ClickException("✗ Error rendering assets")
    elif assets_rendered:
        click.secho("✓ Rendered assets", fg="green", bold=True)


@hg.command("migrate-configs", help="Copy YAML examples to usable config files")
def migrateconfig():
    """Copies example configuration files to usable config files"""
    try:
        click.secho("Migrating example config files...", fg="black")
        config_dir = os.path.join(working_directory, "hyperglass/configuration/")
        examples = glob.iglob(os.path.join(config_dir, "*.example"))
        for f in examples:
            basefile, extension = os.path.splitext(f)
            if os.path.exists(basefile):
                click.secho(f"{basefile} already exists", fg="blue")
            else:
                try:
                    cp(f, basefile)
                    click.secho(f"✓ Migrated {basefile}", fg="green")
                except:
                    click.secho(f"✗ Failed to migrate {basefile}", fg="red")
                    raise
        click.secho(
            "✓ Successfully migrated example config files", fg="green", bold=True
        )
    except:
        click.secho("✗ Error migrating example config files", fg="red", bold=True)
        raise


@hg.command("migrate-gunicorn", help="Copy Gunicorn example to usable config file")
def migrategunicorn():
    """Copies example Gunicorn config file to a usable config"""
    try:
        import hyperglass
    except ImportError as error_exception:
        click.secho(f"Error while importing hyperglass:\n{error_exception}", fg="red")
    try:
        click.secho("Migrating example Gunicorn configuration...", fg="black")
        hyperglass_root = os.path.dirname(hyperglass.__file__)
        ex_file = os.path.join(hyperglass_root, "gunicorn_config.py.example")
        basefile, extension = os.path.splitext(ex_file)
        newfile = basefile
        if os.path.exists(newfile):
            click.secho(f"{newfile} already exists", fg="blue")
        else:
            try:
                cp(ex_file, newfile)
                click.secho(
                    f"✓ Successfully migrated Gunicorn configuration to: {newfile}",
                    fg="green",
                    bold=True,
                )
            except:
                click.secho(f"✗ Failed to migrate {newfile}", fg="red")
                raise
    except:
        click.secho(
            "✗ Error migrating example Gunicorn configuration", fg="red", bold=True
        )
        raise


@hg.command("migrate-systemd", help="Copy Systemd example to OS")
@click.option(
    "-d", "--directory", default="/etc/systemd/system", help="Destination Directory"
)
def migratesystemd(directory):
    """Copies example systemd service file to /etc/systemd/system/"""
    try:
        click.secho("Migrating example systemd service...", fg="black")
        ex_file_base = "hyperglass.service.example"
        ex_file = os.path.join(working_directory, f"hyperglass/{ex_file_base}")
        basefile, extension = os.path.splitext(ex_file_base)
        newfile = os.path.join(directory, basefile)
        if os.path.exists(newfile):
            click.secho(f"{newfile} already exists", fg="blue")
        else:
            try:
                cp(ex_file, newfile)
                click.secho(
                    f"✓ Successfully migrated systemd service to: {newfile}",
                    fg="green",
                    bold=True,
                )
            except:
                click.secho(f"✗ Failed to migrate {newfile}", fg="red")
                raise
    except:
        click.secho("✗ Error migrating example systemd service", fg="red", bold=True)
        raise


@hg.command(
    "update-permissions",
    help="Fix ownership & permissions of hyperglass project directory",
)
@click.option("--user", default="www-data")
@click.option("--group", default="www-data")
def fixpermissions(user, group):
    """Effectively runs `chmod` and `chown` on the hyperglass/hyperglass directory"""
    try:
        import hyperglass
    except ImportError as error_exception:
        click.secho(f"Error importing hyperglass:\n{error_exception}")
    hyperglass_root = os.path.dirname(hyperglass.__file__)
    uid = pwd.getpwnam(user).pw_uid
    gid = grp.getgrnam(group).gr_gid
    try:
        for root, dirs, files in os.walk(hyperglass_root):
            for d in dirs:
                full_path = os.path.join(root, d)
                os.chown(full_path, uid, gid)
            for f in files:
                full_path = os.path.join(root, f)
                os.chown(full_path, uid, gid)
            os.chown(root, uid, gid)
        click.secho(
            "✓ Successfully changed hyperglass/ ownership", fg="green", bold=True
        )
    except:
        click.secho("✗ Failed to change hyperglass/ ownership", fg="red", bold=True)
        raise
    try:
        for root, dirs, files in os.walk(hyperglass_root):
            for d in dirs:
                full_path = os.path.join(root, d)
                os.chmod(full_path, 0o744)
            for f in files:
                full_path = os.path.join(root, f)
                os.chmod(full_path, 0o744)
            os.chmod(root, 0o744)
        click.secho(
            "✓ Successfully changed hyperglass/ permissions", fg="green", bold=True
        )
    except:
        click.secho("✗ Failed to change hyperglass/ permissions", fg="red", bold=True)
        raise


@hg.command("generate-secret", help="Generate agent secret")
@click.option("-l", "--length", default=32, help="Secret length")
def generate_secret(length):
    import secrets

    gen_secret = secrets.token_urlsafe(length)
    click.echo(
        NL
        + click.style("Secret: ", fg="white")
        + click.style(gen_secret, fg="magenta", bold=True)
        + NL
    )


if __name__ == "__main__":
    hg()
