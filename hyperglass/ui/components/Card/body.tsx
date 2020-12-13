import { Flex } from '@chakra-ui/react';
import { useColorValue } from '~/context';

import type { ICardBody } from './types';

export const CardBody = (props: ICardBody) => {
  const { onClick, ...rest } = props;
  const bg = useColorValue('white', 'original.dark');
  const color = useColorValue('original.dark', 'white');
  return (
    <Flex
      bg={bg}
      w="100%"
      maxW="100%"
      rounded="md"
      color={color}
      onClick={onClick}
      overflow="hidden"
      borderWidth="1px"
      direction="column"
      {...rest}
    />
  );
};