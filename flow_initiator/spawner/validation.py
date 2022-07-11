"""
   Copyright (C) Mov.ai  - All Rights Reserved
   Unauthorized copying of this file, via any medium is strictly prohibited
   Proprietary and confidential

   Developers:
   - Manuel Silva (manuel.silva@mov.ai) - 2021

    Spawner commands validator
"""

from typing import Optional
from movai_core_shared.exceptions import CommandError, ActiveFlowError
from movai_core_shared.logger import Log

log = Log.get_logger("spawner.mov.ai")

METHOD = 0
HELP = 1


def format_msg(error: str, msg: str, kwargs: dict) -> str:
    """Format error message"""
    return f"\n{error}:\n" f"    {kwargs}\n" f"{msg}"


def requires_active_flow(**kwargs) -> bool:
    """Raise and exception if the command requires an active flow
    but there is no active flow
    """

    # __COMMANDS__ that require an active flow
    req_active_flow = ["TRANS", "RUN", "KILL", "STOP"]

    if kwargs["command"] in req_active_flow and kwargs["active_flow"] is None:
        raise ActiveFlowError(
            format_msg(
                "ActiveFlowError",
                f"Command {kwargs['command']} requires an active flow",
                kwargs,
            )
        )

    return True


class CommandValidator(dict):
    """Command validations"""

    def __init__(self, commands: dict):
        methods_dict = {key: item[0] for key, item in commands.items()}
        super().__init__(methods_dict)
        self.commands = commands

    def help(self, command: str) -> Optional[str]:
        if command not in self.commands.keys():
            log.error(
                f"Command {command} not found. Push 'command=HELP' to get available commands."
            )
            return None
        return self.commands[command][HELP]

    def print_help(self):
        for command, value in self.commands.items():
            log.info("{:>14}: {}".format(command, value[HELP]))

    def validate_command(self, **kwargs) -> bool:
        """Raise an exception if the command is not valid"""

        res = [self.__is_implemented(**kwargs), requires_active_flow(**kwargs)]

        return all(res)

    def __is_implemented(self, **kwargs) -> bool:
        """Raise an exception if the command is not implemented"""

        if not kwargs["command"] in self.commands.keys():
            raise CommandError(
                format_msg(
                    "CommandError",
                    f"Command {kwargs['command']} not implemented.",
                    kwargs,
                )
            )

        return True

    def __requires_active_flow(self, **kwargs) -> bool:
        """Raise and exception if the command requires an active flow
        but there is no active flow
        """

        # __COMMANDS__ that require an active flow
        req_active_flow = ["TRANS", "RUN", "KILL", "STOP"]

        if kwargs["command"] in req_active_flow and kwargs["active_flow"] is None:
            raise ActiveFlowError(
                self.__format_msg(
                    "ActiveFlowError",
                    f"Command {kwargs['command']} requires an active flow",
                    kwargs,
                )
            )

        return True

    def __format_msg(self, error: str, msg: str, kwargs: dict) -> str:
        """Format error message"""
        return f"\n{error}:\n" f"    {kwargs}\n" f"{msg}"
