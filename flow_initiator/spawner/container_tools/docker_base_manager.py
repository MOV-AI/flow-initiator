"""
A file for docker base manager
"""

import socket
from functools import wraps
from typing import Callable, Optional

from docker.errors import NotFound, APIError
from deprecated.spawner.exceptions import OrchestratorException
from deprecated.envvars import DOCKER_REGISTRY

from .ttdocker_client import TTDockerClient
from deprecated.logger import Logger

log = Logger("DockerBaseManager")


class DockerBaseManager:
    """
    A base class for all docker managers
    """

    docker_client = property(lambda self: self._docker_client)
    docker_registry = property(lambda self: self._docker_registry)

    def __init__(self, default_labels: Optional[dict] = None):
        self._docker_registry = DOCKER_REGISTRY
        self._docker_client = TTDockerClient()
        self._docker_APIClient = self._docker_client.api

        self._default_labels = dict() if default_labels is None else default_labels
        net_name = f"shared-{socket.gethostname()}"
        try:
            self._shared_network = self._docker_client.networks.get(net_name)
        except NotFound:
            self._shared_network = self._docker_client.networks.create(
                net_name, driver="bridge"
            )


def check_dockerd(func: Callable):
    """
    decorator for checking whether the docker daemon is responding
    Args:
        func: the callback function to run

    Returns: return value of the function

    """

    @wraps(func)
    def _check_dockerd(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except APIError as e:
            log.error(e)
            log.critical("docker daemon not available")
            raise OrchestratorException(e)

    return _check_dockerd
