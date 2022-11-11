"""
   Copyright (C) Mov.ai  - All Rights Reserved
   Unauthorized copying of this file, via any medium is strictly prohibited
   Proprietary and confidential

   Developers:
   - Manuel Silva  (manuel.silva@mov.ai) - 2021
   - Dor Marcous   (Dor@mov.ai) - 2021
"""

import unittest
from flow_initiator.spawner.validation import CommandValidator
from movai_core_shared.exceptions import CommandError, ActiveFlowError


class TestSpawner(unittest.TestCase):
    """
    Test spawner
    """

    def test_command_validation(self):
        """
        Test get_dict
        """

        # implemented commands
        impl_commands = ["START",
                         "STOP",
                         "TRANS",
                         "LOCK",
                         "UNLOCK",
                         "RUN",
                         "KILL",
                         "HELP",
                         "EMERGENCY_SET",
                         "EMERGENCY_UNSET"]

        validator = CommandValidator()

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


if __name__ == '__main__':
    unittest.main()
