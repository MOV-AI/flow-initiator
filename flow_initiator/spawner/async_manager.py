"""
   Copyright (C) Mov.ai  - All Rights Reserved
   Unauthorized copying of this file, via any medium is strictly prohibited
   Proprietary and confidential

   Developers:
   - Erez Zomer (erez@mov.ai) - 2023
   - Dor Marcous (Dor@mov.ai) - 2022
"""
import argparse
import asyncio
import json
import traceback

from movai_core_shared.envvars import (
    DEVICE_NAME,
    FLEET_NAME,
    SPAWNER_BIND_ADDR,
    SPAWNER_DEBUG_MODE,
)
from movai_core_shared.logger import Log
from movai_core_shared.core.zmq.zmq_server import ZMQServer

from dal.scopes.robot import Robot

from flow_initiator.spawner.async_movaicore import Core
from flow_initiator.spawner.async_spawner import Spawner

spawner_logger = "spawner.mov.ai"
LOGGER = Log.get_logger(spawner_logger)
USER_LOGGER = Log.get_user_logger(spawner_logger)


def handle_exception(context):
    """
    Handle Exceptions for all the threads
    Args:
        loop: event loop
        context: the context of the exception

    Returns: None

    """
    msg = context.get("exception", context["message"])
    tb_str = traceback.format_exception(
        etype=type(msg), value=msg, tb=msg.__traceback__
    )
    USER_LOGGER.error("\n" + "".join(tb_str))


class SpawnerManager(ZMQServer):
    def __init__(self, fargs: argparse.Namespace) -> None:
        server_name = f"{self.__class__.__name__}-{DEVICE_NAME}-{FLEET_NAME}"
        super().__init__(server_name, SPAWNER_BIND_ADDR, SPAWNER_DEBUG_MODE)
        self._logger = LOGGER
        self.loop = asyncio.get_event_loop()
        self.loop.set_exception_handler(handle_exception)
        self.spawner = Spawner(self.loop, Robot(), fargs.verbose, "flow-private")
        self.core = Core(self.spawner, self.loop)
        self.add_parallel_task(self.core.run())

    async def handle(self, buffer: bytes) -> None:
        """The main function to handle incoming requests by ZMQServer.

        Args:
            buffer (bytes): The buffer that the server was able to read.
        """
        try:
            request = json.loads(buffer).get("request")
            req_data = request.get("req_data")
            command_dict = req_data.get("command")
            asyncio.create_task(self.core.spawner.process_command(command_dict))
            response_msg = "Got request & successfully proccessed".encode("utf8")
        except json.JSONDecodeError as e:
            self._logger.error(f"can't parse command: {buffer}")
            self._logger.error(e)
            response_msg = "can't parse command: {buffer}".encode("utf8")
        finally:
            await self._socket.send_multipart(response_msg)

    async def startup(self):
        """A funtion which is called once at server startup and can be used for initializing
        other tasks.
        """
        await self.core.run()
