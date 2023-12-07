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

from beartype import beartype

from movai_core_shared.logger import Log

from dal.scopes.robot import Robot

from flow_initiator.spawner.spawner_core import SpawnerCore
from flow_initiator.spawner.spawner import Spawner
from flow_initiator.spawner.spawner_server import SpawnerServer

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
