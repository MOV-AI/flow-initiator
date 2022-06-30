"""

   Copyright (C) Mov.ai  - All Rights Reserved
   Unauthorized copying of this file, via any medium is strictly prohibited
   Proprietary and confidential

   Developers:
   - Dor Marcous  (dor@mov.ai) - 2021
"""
from typing import List

from elements import BaseElement


class NodeletLauncher(BaseElement):
    """
    A class to control nodelets
    Need to get the nodelet libs and move it to a volume
    and attach it to the container that runs the nodelet master
    """

    def kill(self):
        """
        TODO
        A kill function for stopping
        Returns:

        """

    async def is_running(self) -> bool:
        """
        TODO
        A kill function for stopping
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
    def eid(self) -> Tuple[str, int]:
        """
        TODO
        A kill function for stopping
        Returns: Return the id of the element
                 Return as a tuple of (str) name of the machine, (int) process id
        """

    @property
    def return_code(self) -> Optional[int]:
        """
        TODO
        A kill function for stopping
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

    def send_terminate_signal(self):
        """
        TODO
        A kill function for stopping
        Send terminate signal to process

        """

    def send_kill_signal(self):
        """
        TODO
        A kill function for stopping
        Send kill signal to process

        """

    async def run(self):
        """
        TODO
        runs the nodelet, or start it again if stopped

        Returns: None

        """
