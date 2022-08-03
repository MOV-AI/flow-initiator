"""

   Copyright (C) Mov.ai  - All Rights Reserved
   Unauthorized copying of this file, via any medium is strictly prohibited
   Proprietary and confidential

   Developers:
   - Dor Marcous  (dor@mov.ai) - 2021
"""
import asyncio
import signal
from typing import Tuple, Optional

from flow_initiator.spawner.elements import BaseElement
from flow_initiator.spawner.exceptions import RunError


class ProcessElement(BaseElement):
    """
    A class to control processes
    """

    @property
    def eid(self) -> Tuple[str, int]:
        return "HOST", self.proc.pid

    def __init__(self, *args, **kwargs):
        """
        Start a new process
        Args:
            command (list): list of commands
            cwd (str): specific working directory
            wait (bool) : if to wait for the process to terminate
            env (list) : environment variables
            **kwargs:
        """
        super().__init__(*args, **kwargs)
        self.cwd = kwargs.get("cwd", None)
        self.env = kwargs.get("wait", None)
        stdout = kwargs.get("stdout", None)
        if self.commands is None or stdout is None:
            self._logger.error("RUN command failed.")
            raise RunError("missing command line")
        self._stdout = stdout
        self.proc = None

    async def run(self):
        """
        Run the process on the host
        Returns: None

        """
        self.proc = await asyncio.create_subprocess_exec(
            *self.commands,
            stdin=None,
            stderr=self._stdout,
            stdout=self._stdout,
            cwd=self.cwd,
            env=self.env,
        )

    async def is_running(self) -> bool:
        """
        Check if a process is running
        Returns: True if it's running

        """
        try:
            await self.proc.communicate()
        except (BrokenPipeError, ConnectionResetError):
            self._logger.debug(f"{self.eid} process terminated.")
            return False
        return True

    def __del__(self):
        """
        Destructor to kill all the subprocess.
        """
        if self.proc.returncode is None:
            self.proc.kill()

    async def wait(self):
        """
        Wait for the process to finish
        """
        await self.proc.wait()

    async def kill(self):
        """
        A kill function for stopping
        Returns: None

        """
        self._logger.info(
            "Spawner: Trying to terminate process({})".format(self.proc.pid)
        )
        try:
            self.proc.send_signal(signal.SIGINT)
        except ProcessLookupError:
            self._logger.warning("can't kill process can't found it")

        await self.ensure_process_kill()

    def send_terminate_signal(self):
        """
        send SIGTERM to process
        """
        self.proc.terminate()

    def send_kill_signal(self):
        """
        send SIGKILL to process
        """
        self.proc.kill()

    @property
    def return_code(self) -> Optional[int]:
        """
        getter for the return code
        Returns: Return the exit code of the process, None if it's still running.

        """
        return self.proc.returncode
