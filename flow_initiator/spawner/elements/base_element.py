"""

   Copyright (C) Mov.ai  - All Rights Reserved
   Unauthorized copying of this file, via any medium is strictly prohibited
   Proprietary and confidential

   Developers:
   - Dor Marcous  (dor@mov.ai) - 2021
"""
import time

import asyncio
from abc import abstractmethod, ABC
from typing import Tuple, Optional

from flow_initiator.spawner.elements import ElementType
from movai_core_shared.consts import TIMEOUT_PROCESS_SIGINT, TIMEOUT_PROCESS_SIGTERM


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
    def kill(self):
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

    async def ensure_process_kill(
        self, term_time: int, wait_interval: int = 0.5
    ) -> None:
        """Ensure the process dies
        Args:
            term_time (int) : initial termination time
            wait_interval (int) : time inteval between waits
        Returns:
            None
        Raises:
            Exception: if the process is not killed after the timeout
        Notes:
          terminate_process() should have been called before this function and sent SIGTERM to the process
        """
        timeout_term = TIMEOUT_PROCESS_SIGTERM
        timeout_int = TIMEOUT_PROCESS_SIGINT

        sigint_sent = False

        pid = process_key["pid"]
        process = process_key["process"]

        t_max_sigterm = term_time + timeout_term
        t_max_sigint = term_time + timeout_term + timeout_int

        while 1:
            # 1. Get the current time when in a new iteration of the loop
            current_time = time.time()

            # 2. Check if the process has terminated by itself (return_code is not None)
            return_code = process.returncode
            if return_code is not None:
                self._logger.debug(
                    "Node {} ({}) terminated with code {}, SIGINT sent: {}".format(
                        node_name, str(pid), return_code, sigint_sent
                    )
                )
                return return_code

            # check if the process is still alive
            if not psutil.pid_exists(pid):
                self._logger.debug(
                    "Node {} ({}) is not alive anymore, SIGINT sent: {}".format(node_name, str(pid), sigint_sent)
                )
                return None

            # 3. Check if the process needs to be forcefully terminated (SIGINT)
            if current_time > t_max_sigterm:
                if not sigint_sent:
                    self._logger.warning("Sending SIGINT to node {} ({})".format(node_name, str(pid)))
                    process.send_signal(signal.SIGINT)
                    sigint_sent = True

                    # relaunch a new iteration of the loop
                    await asyncio.sleep(wait_interval)
                    continue

            # 4. Check if the process needs to be killed (last call)
            if current_time > t_max_sigint:
                self._logger.error("Sending SIGKILL to node {} ({})".format(node_name, str(pid)))
                process.send_signal(signal.SIGKILL)

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
