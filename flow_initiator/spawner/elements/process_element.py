"""

   Copyright (C) Mov.ai  - All Rights Reserved
   Unauthorized copying of this file, via any medium is strictly prohibited
   Proprietary and confidential

   Developers:
   - Dor Marcous  (dor@mov.ai) - 2021
"""

import asyncio
import signal
import time
from typing import Tuple, Optional

import psutil

from flow_initiator.spawner.elements import BaseElement
from flow_initiator.spawner.exceptions import RunError
from movai_core_shared import TIMEOUT_PROCESS_SIGINT, TIMEOUT_PROCESS_SIGTERM


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
        self.env = kwargs.get("env", None)
        self.node_name = kwargs.get("node_name", None)
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

    async def ensure_process_kill(self, wait_interval: int = 0.5) -> None:
        """Ensure the process dies
        Args:
            wait_interval (int) : time inteval between waits
        Returns:
            None
        Raises:
            Exception: if the process is not killed after the timeout
        Notes:
          send_terminate_signal() should have been called before this function and sent SIGTERM to the process
        """
        timeout_term = TIMEOUT_PROCESS_SIGTERM
        timeout_int = TIMEOUT_PROCESS_SIGINT

        sigint_sent = False

        term_time = time.time()
        print("start Time is now", term_time)
        t_max_sigterm = term_time + timeout_term
        t_max_sigint = term_time + timeout_term + timeout_int
        node_name = self.node_name or "Unknown"
        print("max", t_max_sigint, t_max_sigterm)

        while 1:
            # 1. Get the current time when in a new iteration of the loop
            current_time = time.time()
            print("Time is now", current_time)

            # 2. Check if the process has terminated by itself (return_code is not None)
            return_code = self.proc.returncode
            if return_code is not None:
                self._logger.debug(
                    "Node {} ({}) terminated with code {}, SIGINT sent: {}".format(
                        node_name, str(self.proc.pid), return_code, sigint_sent
                    )
                )
                return return_code

            # check if the process is still alive
            if not psutil.pid_exists(self.proc.pid):
                self._logger.debug(
                    "Node {} ({}) is not alive anymore, SIGINT sent: {}".format(
                        node_name, str(self.proc.pid), sigint_sent
                    )
                )
                return None

            # 3. Check if the process needs to be forcefully terminated (SIGINT)
            if current_time > t_max_sigterm and not sigint_sent:
                self._logger.warning(
                    "Sending SIGINT to node {} ({})".format(
                        node_name, str(self.proc.pid)
                    )
                )
                self.proc.send_signal(signal.SIGINT)
                sigint_sent = True

                # relaunch a new iteration of the loop
                await asyncio.sleep(wait_interval)
                continue

            # 4. Check if the process needs to be killed (last call)
            if current_time > t_max_sigint:
                self._logger.error(
                    "Sending SIGKILL to node {} ({})".format(
                        node_name, str(self.proc.pid)
                    )
                )
                self.proc.send_signal(signal.SIGKILL)
