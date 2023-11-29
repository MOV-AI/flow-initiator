"""
   Copyright (C) Mov.ai  - All Rights Reserved
   Unauthorized copying of this file, via any medium is strictly prohibited
   Proprietary and confidential

   Developers:
   - Manuel Silva (manuel.silva@mov.ai) - 2021

    Spawner exceptions
"""


class NotInstalled(Exception):
    pass


class OrchestratorException(Exception):
    pass


class FailedUpgradeCertificate(OrchestratorException):
    pass


class SystemStartupException(Exception):
    pass


class FirmwareUpdateException(Exception):
    pass


class RobotConfigException(Exception):
    pass


class CommandError(Exception):
    """
    Raise when the command does not exist
    """


class ActiveFlowError(Exception):
    """
    Raise when the command requires an active flow
    """


class RunError(Exception):
    """
    Run error elements exception
    """
