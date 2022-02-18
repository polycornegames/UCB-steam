__version__ = "0.31"

from atlassian.bitbucket import Cloud
from atlassian.bitbucket.cloud.repositories import Repository


# region BITBUCKET
class PolyBitBucket:
    def __init__(self, bitbucket_username: str, bitbucket_app_password: str, bitbucket_workspace: str,
                 bitbucket_repository: str, bitbucket_cloud: bool = True):
        self._bitbucket_username: str = bitbucket_username
        self._bitbucket_app_password: str = bitbucket_app_password
        self._bitbucket_cloud: bool = bitbucket_cloud
        self._bitbucket_workspace: str = bitbucket_workspace
        self._bitbucket_repository: str = bitbucket_repository
        self._bitbucket_connection: Cloud = None
        self._bitbucket_connection_repository: Repository = None

    @property
    def bitbucket_username(self):
        return self._bitbucket_username

    @property
    def bitbucket_app_password(self):
        return self._bitbucket_app_password

    @property
    def bitbucket_cloud(self):
        return self._bitbucket_cloud

    @property
    def bitbucket_workspace(self):
        return self._bitbucket_workspace

    @property
    def bitbucket_repository(self):
        return self._bitbucket_repository

    def connect(self) -> bool:
        self._bitbucket_connection = Cloud(
            username=self._bitbucket_username,
            password=self._bitbucket_app_password,
            cloud=self._bitbucket_cloud)

        try:
            self._bitbucket_connection_repository = self._bitbucket_connection.workspaces.get(
                self._bitbucket_workspace).repositories.get(self._bitbucket_repository)
        except Exception:
            return False

        return True

    def trigger_pipeline(self, branch: str, pipeline_name: str) -> bool:
        try:
            self._bitbucket_connection_repository.pipelines.trigger(branch=branch, pattern=pipeline_name)
        except Exception:
            return False

        return True


# endregion




