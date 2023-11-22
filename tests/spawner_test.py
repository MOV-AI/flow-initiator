"""
   Copyright (C) Mov.ai  - All Rights Reserved
   Unauthorized copying of this file, via any medium is strictly prohibited
   Proprietary and confidential

   Developers:
   - Manuel Silva  (manuel.silva@mov.ai) - 2021
   - Dor Marcous   (Dor@mov.ai) - 2021
"""

import unittest

from movai_core_shared.exceptions import CommandError, ActiveFlowError

from dal.scopes import Robot

from flow_initiator.spawner.validation import CommandValidator
from flow_initiator.spawner.spawner import Spawner

class TestSpawner(unittest.TestCase):
    """
    Test spawner
    """

    spawner = Spawner(Robot())

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

        validator = CommandValidator(
            {
                "START": [self.spawner.process_start, "command='START', flow='flow_name'"],
                "STOP": [self.spawner.process_stop, "command='STOP', flow='flow_name'"],
                "TRANS": [
                    self.spawner.process_transition,
                    "command='TRANS', node='node_name', port='port_name'",
                ],
                "LOCK": [self.spawner.process_lock, "command='LOCK', data={data}"],
                "UNLOCK": [self.spawner.process_unlock, "command='UNLOCK', data={data}"],
                "RUN": [self.spawner.process_run, "command='RUN', node='node_name'"],
                "KILL": [
                    self.spawner.process_kill,
                    "command='KILL', node='node_name', dependencies=bool",
                ],
                "HELP": [self.spawner.process_help, "command='HELP'"],
                "EMERGENCY_SET": [
                    self.spawner.process_emergency_set,
                    "command='EMERGENCY_SET', data={'nodes_to_skip': [<regex>]}",
                ],
                "EMERGENCY_UNSET": [
                    self.spawner.process_emergency_unset,
                    "command='EMERGENCY_UNSET'",
                ],
            }
        )

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
