"""
A file to manage images
"""
import gzip
import subprocess
import platform
from typing import Optional

from docker.models.images import Image
from docker.errors import APIError, ImageNotFound, ImageLoadError
from . import DockerBaseManager, check_dockerd
from movai_core_shared.logger import Log

log = Log.get_logger("ContainerManager")


class ImageManager(DockerBaseManager):
    """
    A class to manage container images
    """

    LOCAL_IMAGES_PATH = "/usr/share/movai/images"

    def __init__(self, default_labels=None):
        super().__init__(default_labels)

    @staticmethod
    def extract_image_name(image: str):
        """
        Extract repo and tag, of the image
        Set latest tag, when no tag is mentions
        Args:
            image: the repo container_name, and could also contain specific tag

        Returns:  repo

        """
        repo, tag = (image, "latest")
        if ":" in image:
            repo, tag = image.rsplit(":", 1)
        return repo, tag

    def pull_image(self, repo: str, tag: str = "latest") -> Optional[Image]:
        """
        Function to pull images from the registry
        Args:
            repo: the repo image name, and could also contain specific tag
            tag: specific tag of the image, default is 'latest'

        Returns:
            (:py:class:`Image` or list): The image that has been pulled.
            If ``all_tags`` is True, the method will return a list
            of :py:class:`Image` objects belonging to this repository.
            None when fails

        """
        log.info(f"Pulling image {repo}:{tag}")
        image_file = None
        try:
            image_file = self._docker_client.images.pull(repo, tag)
        except APIError as e:
            log.error(e)
            param = "-n" if platform.system().lower() == "windows" else "-c"
            server_status = subprocess.call(
                ["ping", param, repo.split("/")[0]],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            if server_status != 0:
                log.error("No internet connection")
            log.error("Failed to pull image, trying to login again")
            try:
                self._docker_client.login(None)
                image_file = self._docker_client.images.pull(repo, tag)
            except APIError as e:
                log.error(e)
                log.error(
                    "Can't pull from the server, please try to login again and see docker logs"
                )
                log.error("Please use: 'sudo journalctl -fu docker.service'")
        return image_file

    @check_dockerd
    def get_image(self, image_name: str) -> Optional[Image]:
        """
        Get image, if not exists, try to pull
        Args:
            image_name:image: the repo container_name, and could also contain specific tag, split with ':'

        Returns:
            Wanted image object, or None if failed

        """
        log.debug(f"Getting image: {image_name}")
        repo, tag = self.extract_image_name(image_name)
        try:
            return self._docker_client.images.get(image_name)
        except ImageNotFound:
            log.debug("Can't find image: {image_name}, trying to pull from the server")
            image = self.pull_image(repo, tag)
            if image is None:
                log.error("Didn't successfully pull, looking for image locally")
                image = self.load_image_locally(repo, tag)
            return image

    def load_image_locally(self, repo: str, tag: str = "latest") -> Optional[Image]:
        """
        Load image from the local docker repository
        # assume no internet connection
        # look for image locally
        Args:
            repo: the repo image name, and could also contain specific tag
            tag: specific tag of the image, default is 'latest'

        Returns:
             (list of :py:class:`Image`): The images.

        """
        log.debug("Loading image locally")
        image_file = None
        filename = self.LOCAL_IMAGES_PATH + "/" + repo.rsplit("/", 1)[-1] + ".tar.gz"
        try:
            with gzip.open(filename, "rb") as fd:
                image_file = self._docker_client.images.load(fd.read())[0]
            log.info("Image loaded")
            # tag it with latest
            image_file.tag(repo, tag)
        except (FileNotFoundError, ImageLoadError) as err:
            log.error(f"Error loading image  {err}")
        return image_file

    def prune_images(self, filters: dict) -> Optional[dict]:
        """
        Delete unused images

        Args:
            filters (dict): Filters to process on the prune list.
                Available filters:
                - dangling (bool):  When set to true (or 1), prune only
                unused and untagged images.

        Returns:
            (dict): A dict containing a list of deleted image IDs and
                the amount of disk space reclaimed in bytes.
        """
        log.debug("prune images")
        return self._docker_client.images.prune(filters)

    def remove_image(
        self, repo: str, tag: str, force: bool = False, noprune: bool = False
    ) -> None:
        """
        Remove an image
        Args:
            repo: the repo image name, and could also contain specific tag
            tag: specific tag of the image, default is 'latest'
            force (bool): Force removal of the image
            noprune (bool): Do not delete untagged parents

        Returns:

        """
        self._docker_client.images.remove(f"{repo}:{tag}", force, noprune)

    @staticmethod
    def tag_image(
        image: Image, new_repo: str, new_tag: str, force: bool = False
    ) -> None:
        """
        Tag this image into a repository. Similar to the ``docker tag``
        command.

        Args:
            image (Image): the image
            new_repo (str): The repository to set for the tag
            new_tag (str): The tag name
            force (bool): Force
        """
        image.tag(new_repo, new_tag, force=force)
