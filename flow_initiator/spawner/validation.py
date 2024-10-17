"""
   Copyright (C) Mov.ai  - All Rights Reserved
   Unauthorized copying of this file, via any medium is strictly prohibited
   Proprietary and confidential

   Developers:
   - Manuel Silva (manuel.silva@mov.ai) - 2021

    Spawner commands validator
"""

import inspect
from typing import Callable, Optional, get_type_hints

from beartype.door import die_if_unbearable
from beartype.roar import (
    BeartypeDecorHintNonpepException,
    BeartypeDecorHintPepUnsupportedException,
    BeartypeDoorHintViolation,
)

from movai_core_shared.exceptions import ActiveFlowError, CommandError
from movai_core_shared.logger import Log

log = Log.get_logger("spawner.mov.ai")

METHOD = 0
HELP = 1


def format_msg(error: str, msg: str, kwargs: dict) -> str:
    """Format error message"""
    return f"\n{error}:\n    {kwargs}\n{msg}"


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


def validate_args_against_function(args: dict, func: Callable):
    """Checks if the types of all the arguments sent match
    what the function expects (considering its type hints)"""
    # Get the signature of the function
    sig = inspect.signature(func)

    # Get the type hints of the function
    type_hints = get_type_hints(func)

    for key, value in args.items():
        # Check if the key exists in the function's parameters
        if key not in sig.parameters:
            raise ValueError(
                f"Unexpected argument '{key}' for function '{func.__name__}'"
            )

        # Check if the key has an associated type hint, and if the type matches
        expected_type = type_hints.get(key)
        if not expected_type:
            continue

        try:
            die_if_unbearable(value, expected_type)
        except BeartypeDecorHintNonpepException:
            # problem with the typing in the codebase, let's just log and move on
            log.debug(
                "There's a typing problem in the flow-initiator command function '%s'",
                func,
            )
        except BeartypeDecorHintPepUnsupportedException:
            # beartype doesn't support this, nothing we can do
            pass
        except BeartypeDoorHintViolation as exc:
            raise TypeError(
                f"Argument '{key}' expected type '{expected_type.__name__}', "
                f"but got '{type(value).__name__}'"
            ) from exc

    # Check if all required arguments are provided
    for param in sig.parameters.values():
        if param.default is param.empty and param.name not in args:
            raise ValueError(f"Missing required argument: '{param.name}'")


class CommandValidator(dict):
    """Command validations"""

    def __init__(self, commands: dict):
        methods_dict = {key: item[0] for key, item in commands.items()}
        super().__init__(methods_dict)
        self.commands = commands

    def help(self, command: str) -> Optional[str]:
        if command not in self.commands:
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

        self.__is_implemented(**kwargs)
        requires_active_flow(**kwargs)
        self.validate_args(**kwargs)
        return True

    def __is_implemented(self, **kwargs) -> None:
        """Raise an exception if the command is not implemented"""

        if kwargs["command"] not in self.commands:
            raise CommandError(
                format_msg(
                    "CommandError",
                    f"Command {kwargs['command']} not implemented.",
                    kwargs,
                )
            )

    def validate_args(self, **kwargs) -> None:
        """Raises a CommandError if the arguments sent don't match what the function expects"""

        args = kwargs.copy()
        command = args.pop("command")
        args.pop("active_flow")  # this will be checked by another function
        try:
            validate_args_against_function(args, self.commands[command][METHOD])
        except (TypeError, ValueError) as e:
            raise CommandError(
                format_msg(
                    "CommandError",
                    f"Arguments are invalid for command {kwargs['command']}: {e}",
                    kwargs,
                )
            )
