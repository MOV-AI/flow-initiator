"""
   Copyright (C) Mov.ai  - All Rights Reserved
   Unauthorized copying of this file, via any medium is strictly prohibited
   Proprietary and confidential

   Developers:
   - Manuel Silva  (manuel.silva@mov.ai) - 2021
   - Dor Marcous   (Dor@mov.ai) - 2021
"""

import unittest
from unittest import mock
import pytest

from flow_initiator.spawner.spawner import Spawner
from movai_core_shared.exceptions import CommandError, ActiveFlowError

from flow_initiator.spawner.validation import CommandValidator


class TestSpawner(unittest.TestCase):
    """
    Test spawner
    """

    def setUp(self) -> None:
        with mock.patch("dal.scopes.robot.MovaiDB"):
            with mock.patch("dal.scopes.robot.MessageClient"):
                from dal.scopes.robot import Robot

                self.robot = mock.MagicMock(spec=Robot)
                self.robot.RobotName = "robot_123"

    def test_command_validation(self):
        """
        Test get_dict
        """

        # implemented commands
        impl_commands = [
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

        with mock.patch("flow_initiator.spawner.spawner.open"):
            validator = Spawner(self.robot).commands

        with self.subTest():
            command = {"command": "TRANS", "active_flow": None}

            with self.assertRaises(ActiveFlowError):
                validator.validate_command(**command)

        with self.subTest():
            command = {"command": "UNKNOWN", "active_flow": None}

            with self.assertRaises(CommandError):
                validator.validate_command(**command)

        for name in impl_commands:
            with self.subTest():
                command = {"command": name, "active_flow": "flow"}

                self.assertTrue(validator.validate_command(**command))


if __name__ == "__main__":
    unittest.main()
