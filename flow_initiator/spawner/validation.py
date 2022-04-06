"""
   Copyright (C) Mov.ai  - All Rights Reserved
   Unauthorized copying of this file, via any medium is strictly prohibited
   Proprietary and confidential

   Developers:
   - Manuel Silva (manuel.silva@mov.ai) - 2021

    Spawner commands validator
"""

from movai_core_shared.exceptions import CommandError, ActiveFlowError


class CommandValidator:
    """Command validations"""

    __COMMANDS__ = [
        "START",
        "STOP",
        "TRANS",
        "LOCK",
        "UNLOCK",
        "RUN",
        "KILL",
        "HELP",
        "EMERGENCY_SET",
        "EMERGENCY_UNSET",
    ]

    def validate_command(self, **kwargs) -> bool:
        """Raise an exception if the command is not valid"""

        res = [self.__is_implemeted(**kwargs), self.__requires_active_flow(**kwargs)]

        return all(res)

    def __is_implemeted(self, **kwargs) -> bool:
        """Raise an exception if the command is not implemented"""

        if not kwargs["command"] in self.__COMMANDS__:
            raise CommandError(
                self.__format_msg(
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
