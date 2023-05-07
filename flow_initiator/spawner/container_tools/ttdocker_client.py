import docker
from docker.errors import DockerException
import requests
from movai_core_shared.logger import Log
from movai_core_shared.envvars import DOCKERD_ATTEMPTS

log = Log.get_logger("Docker-Client")


class TTAPIClient(docker.APIClient):
    """Timeout Tolerant Docker's API Client

    Override parent's (requests.Session)
    methods to retry on timeout.

    Probably not the fanciest way, in our current situation
    (docker is http/unix), the timeout is ignorable.
    """

    num_of_attempts = 1

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        try:
            self.num_of_attempts = int(DOCKERD_ATTEMPTS)
            if self.num_of_attempts <= 0:
                raise ValueError()
        except ValueError:
            log.critical("wrong value: DOCKERD_ATTEMPTS must be positive integer")

    def multiple_attempts(self, function, *args, **kwargs):
        """
        loop for multiple attempts
        """
        for _ in range(self.num_of_attempts):
            try:
                return function(*args, **kwargs)
            except requests.exceptions.Timeout as e:
                log.warning(f"Timeout reading: {type(e).__qualname__}: {str(e)}")
        log.critical("Can't reach docker daemon")

    # todo: check how to do it for all methods
    def get(self, *args, **kwargs):
        return self.multiple_attempts(super().get, *args, **kwargs)

    def post(self, *args, **kwargs):
        return self.multiple_attempts(super().post, *args, **kwargs)

    def put(self, *args, **kwargs):
        return self.multiple_attempts(super().put, *args, **kwargs)

    def delete(self, *args, **kwargs):
        return self.multiple_attempts(super().delete, *args, **kwargs)

    def load_image(self, *args, **kwargs):
        return self.multiple_attempts(super().load_image, *args, **kwargs)

    def pull(self, *args, **kwargs):
        return self.multiple_attempts(super().pull, *args, **kwargs)

    def create_container(self, *args, **kwargs):
        return self.multiple_attempts(super().create_container, *args, **kwargs)

    def start(self, container, *args, **kwargs):
        return self.multiple_attempts(super().start, container, *args, **kwargs)


class TTDockerClient(docker.DockerClient):
    """Timeout Tolerant Docker Client

    It uses the TTAPIClient internally
    """

    def __init__(self, *args, **kwargs):
        try:
            super().__init__(*args, **kwargs)
            self.api = TTAPIClient(*args, **kwargs)
        except DockerException as e:
            self.api = None
            log.critical(f"Can't reach docker daemon: {type(e).__qualname__}: {str(e)}")
