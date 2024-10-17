"""
   Copyright (C) Mov.ai  - All Rights Reserved
   Unauthorized copying of this file, via any medium is strictly prohibited
   Proprietary and confidential

   Developers:
   - Erez Zomer (erez@mov.ai) - 2023
"""
import asyncio
import json


from beartype import beartype

from movai_core_shared.envvars import (
    DEVICE_NAME,
    FLEET_NAME,
    SPAWNER_BIND_ADDR,
    SPAWNER_DEBUG_MODE,
)
from movai_core_shared.logger import Log
from movai_core_shared.core.zmq.zmq_server import ZMQServer

from flow_initiator.spawner.spawner import Spawner

SPAWNER_LOGGER = "spawner.mov.ai"
LOGGER = Log.get_logger(SPAWNER_LOGGER)
USER_LOGGER = Log.get_user_logger(SPAWNER_LOGGER)


class SpawnerServer(ZMQServer):
    """The spawner server class is responsible for listening for ZMQ commands."""

    @beartype
    def __init__(self, spawner: Spawner) -> None:
        server_name = f"{self.__class__.__name__}-{DEVICE_NAME}-{FLEET_NAME}"
        zmq_bind_addr = SPAWNER_BIND_ADDR
        super().__init__(server_name, zmq_bind_addr, SPAWNER_DEBUG_MODE)
        self.spawner = spawner

    async def handle(self, buffer: bytes) -> None:
        """The main function to handle incoming requests by ZMQServer.

        Args:
            buffer (bytes): The buffer that the server was able to read.
        """
        try:
            if len(buffer) == 3:
                # in case sender just use send
                msg_index = 2
            else:
                # in case when sending json
                msg_index = 1
            msg = buffer[msg_index]
            if msg is None:
                return
            request = json.loads(msg)
            request = request.get("request")
            req_data = request.get("req_data")
            command_dict = req_data.get("command_data")
            asyncio.create_task(self.spawner.process_command(command_dict))
            response_msg = "Got request & successfully proccessed".encode("utf8")
        except json.JSONDecodeError as exc:
            self._logger.error(f"can't parse command: {buffer}")
            self._logger.error(exc)
            response_msg = "can't parse command: {buffer}".encode("utf8")

        await self._socket.send_multipart([response_msg])
