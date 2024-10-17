"""

   Copyright (C) Mov.ai  - All Rights Reserved
   Unauthorized copying of this file, via any medium is strictly prohibited
   Proprietary and confidential

   Developers:
   - Dor Marcous  (dor@mov.ai) - 2021
"""
import asyncio
import time
from abc import ABC, abstractmethod
from typing import Optional, Tuple

from movai_core_shared.consts import (TIMEOUT_PROCESS_SIGINT,
                                      TIMEOUT_PROCESS_SIGTERM)

from flow_initiator.spawner.elements import ElementType
from flow_initiator.spawner.exceptions import RunError


class BaseElement(ABC):
    """
    A base function for controlling elements
    """

    Type: ElementType = None
    TIMES_TO_TRY = 500

    def __init__(self, *args, **kwargs):
        """
        base constructor for all elements
        Args:
            self:
            **kwargs: parameters to run element


        """
        self._logger = kwargs.pop("logger", None)
        if args is not None and len(args) > 1:
            self.commands = args
        else:
            self.commands = kwargs.get("command", None)

    @abstractmethod
    async def run(self):
        """
        Run function for the spawner
        """

    @abstractmethod
    async def kill(self):
        """
        A kill function for stopping
        Returns:

        """

    @abstractmethod
    async def is_running(self) -> bool:
        """
        abstract method to check if element is running
        Returns: bool whether element is running

        """

    def eid_str(self) -> str:
        """
        Get eid in pretty string
        Returns: Str with the format 'machine: {name_of_machine} PID: {pid} '

        """
        machine, pid = self.eid
        return f"machine: {machine}, PID: {pid}"

    @property
    @abstractmethod
    def eid(self) -> Tuple[str, int]:
        """
        Returns: Return the id of the element
                 Return as a tuple of (str) name of the machine, (int) process id
        """

    @property
    @abstractmethod
    def return_code(self) -> Optional[int]:
        """
        get the return code of the element when it closed
        Returns: int represent return code, None if it's still running

        """

    async def ensure_process_kill(self) -> None:
        """
        Ensure the process dies
        # process.terminate() -> Send SIGTERM
        # process.kill()      -> Send SIGKILL
        """

        timeout_int = TIMEOUT_PROCESS_SIGINT
        timeout_term = TIMEOUT_PROCESS_SIGTERM

        sigterm_sent = False

        t_init = time.time()
        for _ in range(self.TIMES_TO_TRY):
            current_time = time.time()

            if self.return_code is not None:
                return

            if current_time > t_init + timeout_int:
                if not sigterm_sent:
                    self._logger.error(f"Sending SIGTERM to process {self.eid_str()}")
                    self.send_terminate_signal()
                    sigterm_sent = True

            if current_time > t_init + timeout_int + timeout_term:
                self._logger.error(f"Sending SIGKILL to process {self.eid_str()}")
                self.send_kill_signal()
                return
            await asyncio.sleep(0.2)
        # if after 100 seconds, the process can't be killed raise an error
        raise RunError("Can't kill process")

    @abstractmethod
    def send_terminate_signal(self):
        """
        Send terminate signal to process

        """

    @abstractmethod
    def send_kill_signal(self):
        """
        Send kill signal to process

        """
