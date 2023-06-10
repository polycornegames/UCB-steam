from typing import Optional, Final, List

from atlassian.bitbucket import Cloud
from atlassian.bitbucket.cloud.repositories import Repository

from libraries import LOGGER
from libraries.Unity.classes import BuildTarget
from libraries.hook import Hook
from libraries.logger import LogLevel

# region ERRORS NUMBER
# must be over 10000
BITBUCKET_CONNECTION_FAILED: Final[int] = 10801
BITBUCKET_PIPELINE_TRIGGER_FAILED: Final[int] = 10802
BITBUCKET_CONNECTION_TEST_FAILED: Final[int] = 10803


# endregion


class PolyBitBucket:
    def __init__(self, bitbucket_username: str, bitbucket_app_password: str, bitbucket_workspace: str,
                 bitbucket_repository: str, bitbucket_cloud: bool = True):
        self._bitbucket_username: str = bitbucket_username
        self._bitbucket_app_password: str = bitbucket_app_password
        self._bitbucket_cloud: bool = bitbucket_cloud
        self._bitbucket_workspace: str = bitbucket_workspace
        self._bitbucket_repository: str = bitbucket_repository
        self._bitbucket_connection: Optional[Cloud] = None
        self._bitbucket_connection_repository: Optional[Repository] = None

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
        except Exception as e:
            print(e)
            return False

        return True


class BitBucketHook(Hook):
    def __init__(self, base_path: str, home_path: str, check_project_version: bool, parameters: dict, notified: bool = False):
        super().__init__(base_path, home_path, check_project_version, parameters, notified)
        self.name = "bitbucket"

        if 'bitbucket' not in self.parameters.keys():
            return

        self._already_notified_build_target: List[str] = list()

        self.username: str = self.parameters['bitbucket']['username']
        self.app_password: str = self.parameters['bitbucket']['app_password']
        self.workspace: str = self.parameters['bitbucket']['workspace']
        self.repository: str = self.parameters['bitbucket']['repository']
        self.bitbucket_connection: Optional[PolyBitBucket] = None

        if 'enabled' in self.parameters[self.name].keys():
            self.enabled = self.parameters[self.name]['enabled']

    def install(self, simulate: bool = False) -> int:
        pass

    def test(self) -> int:
        LOGGER.log("Testing Bitbucket connection...", end="")
        BITBUCKET: PolyBitBucket = PolyBitBucket(bitbucket_username=self.username,
                                                 bitbucket_app_password=self.app_password,
                                                 bitbucket_cloud=True,
                                                 bitbucket_workspace=self.workspace,
                                                 bitbucket_repository=self.repository)

        if not BITBUCKET.connect():
            LOGGER.log("Error connecting to Bitbucket", log_type=LogLevel.LOG_ERROR, no_date=True)
            return BITBUCKET_CONNECTION_TEST_FAILED

        LOGGER.log("OK", log_type=LogLevel.LOG_SUCCESS, no_date=True)

        return 0

    def notify(self, build_target: BuildTarget, simulate: bool = False) -> int:
        LOGGER.log(f"  Notifying {self.name} for [{build_target.name}]...", end="")
        ok: bool = False

        self.bitbucket_connection = PolyBitBucket(bitbucket_username=self.username,
                                                  bitbucket_app_password=self.app_password,
                                                  bitbucket_cloud=True,
                                                  bitbucket_workspace=self.workspace,
                                                  bitbucket_repository=self.repository)

        if build_target.name not in self._already_notified_build_target:
            self._already_notified_build_target.append(build_target.name)

            if not simulate:
                ok = self.bitbucket_connection.connect()
                if not ok:
                    return BITBUCKET_CONNECTION_FAILED

                ok = self.bitbucket_connection.trigger_pipeline(
                    build_target.parameters['branch'],
                    build_target.parameters['pipeline'])

                if not ok:
                    return BITBUCKET_PIPELINE_TRIGGER_FAILED

        LOGGER.log("OK", log_type=LogLevel.LOG_SUCCESS, no_date=True)

        return 0
