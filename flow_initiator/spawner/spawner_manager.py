"""
   Copyright (C) Mov.ai  - All Rights Reserved
   Unauthorized copying of this file, via any medium is strictly prohibited
   Proprietary and confidential

   Developers:
   - Erez Zomer (erez@mov.ai) - 2023
"""
import argparse
import asyncio
import traceback

from dal.scopes.robot import Robot
from movai_core_shared.logger import Log

from flow_initiator.spawner.spawner import Spawner
from flow_initiator.spawner.spawner_core import SpawnerCore
from flow_initiator.spawner.spawner_server import SpawnerServer

SPAWNER_LOGGER = "spawner.mov.ai"
LOGGER = Log.get_logger(SPAWNER_LOGGER)
USER_LOGGER = Log.get_user_logger(SPAWNER_LOGGER)


def handle_exception(loop: asyncio.AbstractEventLoop, context: dict):
    """
    Handle Exceptions for all the threads
    Args:
        loop: event loop
        context: the context of the exception

    Returns: None

    """
    exc = context.get("exception")
    if exc:
        message = traceback.format_exception(etype=type(exc), value=exc, tb=exc.__traceback__)
    else:
        message = [context["message"]]
    USER_LOGGER.error("\n" + "".join(message))


class SpawnerManager:
    """The SpawnerManager is the actual entrypoing to the Spawner app."""

    def __init__(self, fargs: argparse.Namespace) -> None:
        self._logger = USER_LOGGER
        self._loop = None
        self.spawner = Spawner(Robot(), fargs.verbose)
        self.core = SpawnerCore(self.spawner)
        self.server = SpawnerServer(self.spawner)

    def run(self):
        """Starts the main loop."""
        asyncio.run(self.start())

    async def start(self):
        """The main coroutine for starting the various components."""
        self._loop = asyncio.get_running_loop()
        self._loop.set_exception_handler(handle_exception)
        self.spawner.run()
        self.core.run()
        await self.server.spin()

    def shutdown(self):
        """ Shutdown core and ZMQ server """
        self.core.shutdown()
        self.server.stop()
