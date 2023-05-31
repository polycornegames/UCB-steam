import os
import shutil
import stat
import sys
from typing import Final
from zipfile import ZipFile

import requests

from libraries import LOGGER
from libraries.Unity.classes import BuildTarget
from libraries.common import errors
from libraries.logger import LogLevel
from libraries.store import Store

# region ERRORS NUMBER
# must be over 10000
EPIC_CREATE_DIRECTORY1_FAILED: Final[int] = 10801
EPIC_CREATE_DIRECTORY2_FAILED: Final[int] = 10802
EPIC_CREATE_DIRECTORY3_FAILED: Final[int] = 10803
EPIC_CANNOT_UPLOAD: Final[int] = 10804
EPIC_CANNOT_DOWNLOAD: Final[int] = 10805
EPIC_CANNOT_UNZIP: Final[int] = 10806
EPIC_MISSING_PARAMETER: Final[int] = 10807


# endregion


class Epic(Store):
    def __init__(self, base_path: str, home_path: str, build_path: str, download_path: str, check_project_version: bool,
                 parameters: dict,
                 built: bool = False):
        super().__init__(base_path, home_path, build_path, download_path, check_project_version, parameters, built)
        self.name = "epic"

        if 'epic' not in self.parameters.keys():
            LOGGER.log("Configuration file have no 'epic' section", log_type=LogLevel.LOG_ERROR)
            return

        if 'client_id' not in self.parameters['epic'].keys():
            LOGGER.log("'epic' configuration file section have no 'client_id' value", log_type=LogLevel.LOG_ERROR)
            return

        if 'client_secret' not in self.parameters['epic'].keys():
            LOGGER.log("'epic' configuration file section have no 'client_secret' value", log_type=LogLevel.LOG_ERROR)
            return

        if 'org_id' not in self.parameters['epic'].keys():
            LOGGER.log("'epic' configuration file section have no 'org_id' value", log_type=LogLevel.LOG_ERROR)
            return

        if 'product_id' not in self.parameters['epic'].keys():
            LOGGER.log("'epic' configuration file section have no 'product_id' value", log_type=LogLevel.LOG_ERROR)
            return

        self.client_id: str = self.parameters['epic']['client_id']
        self.client_secret: str = self.parameters['epic']['client_secret']
        self.org_id: str = self.parameters['epic']['org_id']
        self.product_id: str = self.parameters['epic']['product_id']

        self.artifact_test_id: str = ""
        if 'artifact_test_id' in self.parameters['epic'].keys():
            self.artifact_test_id = self.parameters['epic']['artifact_test_id']

        self.epic_dir_path: str = f'{base_path}/Epic'
        self.epic_build_path: str = f'{self.epic_dir_path}/build'
        if sys.platform.startswith('linux'):
            self.epic_exe_path: str = f'{self.epic_dir_path}/Engine/Binaries/Linux/BuildPatchTool'
        elif sys.platform.startswith('win32'):
            self.epic_exe_path: str = f'{self.epic_dir_path}/Engine/Binaries/Win64/BuildPatchTool.exe'

    def install(self, simulate: bool = False) -> int:
        ok: int = 0
        LOGGER.log("Creating folder structure for Build Patch Tool...", end="")
        if not simulate:
            if not os.path.exists(self.epic_dir_path):
                os.mkdir(self.epic_dir_path)

                if not os.path.exists(self.epic_dir_path):
                    LOGGER.log(f"Error creating directory {self.epic_dir_path} for {self.name}",
                               log_type=LogLevel.LOG_ERROR, no_date=True)
                    return EPIC_CREATE_DIRECTORY1_FAILED
            if not os.path.exists(self.epic_build_path):
                os.mkdir(self.epic_build_path)

                if not os.path.exists(self.epic_build_path):
                    LOGGER.log(f"Error creating directory {self.epic_build_path} for {self.name}",
                               log_type=LogLevel.LOG_ERROR, no_date=True)
                    return EPIC_CREATE_DIRECTORY2_FAILED

            LOGGER.log("OK", log_type=LogLevel.LOG_SUCCESS, no_date=True)
        else:
            LOGGER.log("Skipped", log_type=LogLevel.LOG_SUCCESS, no_date=True)

        LOGGER.log("Downloading Build Patch Tool...", end="")
        if not simulate:
            if not os.path.exists(self.epic_exe_path):
                epic_url = 'https://epicgames-download1.akamaized.net/Builds/BuildPatchTool/Installers/BuildPatchTool_1.5.1.zip'
                zip_path = f'{self.epic_dir_path}/BuildPatchTool_1.5.1.zip'

                request = requests.get(epic_url, allow_redirects=True)
                open(zip_path, 'wb').write(request.content)

                if not os.path.exists(zip_path):
                    LOGGER.log("Error downloading Build Patch Tool", log_type=LogLevel.LOG_ERROR, no_date=True)
                    return EPIC_CANNOT_DOWNLOAD

                unzipped: bool = False
                try:
                    with ZipFile(zip_path, "r") as zipObj:
                        zipObj.extractall(self.epic_dir_path)
                        unzipped = True
                        LOGGER.log("OK", log_type=LogLevel.LOG_SUCCESS, no_date=True)
                except IOError:
                    unzipped = False

                if not unzipped:
                    LOGGER.log(f'Error unzipping Build Patch Tool {zip_path} to {self.epic_dir_path}',
                               log_type=LogLevel.LOG_ERROR,
                               no_date=True)
                    return EPIC_CANNOT_UNZIP

                st = os.stat(self.epic_exe_path)
                os.chmod(self.epic_exe_path, st.st_mode | stat.S_IEXEC)

                LOGGER.log("OK", log_type=LogLevel.LOG_SUCCESS, no_date=True)
            else:
                LOGGER.log("OK (dependencies already met)", log_type=LogLevel.LOG_SUCCESS, no_date=True)
        else:
            LOGGER.log("Skipped", log_type=LogLevel.LOG_SUCCESS, no_date=True)

        return ok

    def test(self) -> int:
        LOGGER.log("Testing Build Patch Tool connection...", end="")
        if self.artifact_test_id:
            cmd = f'{self.epic_exe_path} -OrganizationId="{self.org_id}" -ProductId="{self.product_id}" -ArtifactId="{self.artifact_test_id}" -ClientId="{self.client_id}" -ClientSecret="{self.client_secret}" -mode=ListBinaries 1> nul'
            ok = os.system(cmd)
            if ok != 0:
                LOGGER.log("Error connecting to Build Patch Tool", log_type=LogLevel.LOG_ERROR, no_date=True)
                return 23
            LOGGER.log("OK", log_type=LogLevel.LOG_SUCCESS, no_date=True)
        else:
            LOGGER.log("artifact_test_id id not set in epic store configuration. Cannot test",
                       log_type=LogLevel.LOG_WARNING, no_date=True)

        return 0

    def build(self, app_version: str = "", no_live: bool = False, simulate: bool = False, force: bool = False) -> int:
        build_path: str = ""
        ok: int = 0

        LOGGER.log(f" Cleaning non necessary files...", end="")
        if not simulate and build_path != "":
            filepath: str = f"{build_path}/bitbucket-pipelines.yml"
            if os.path.exists(filepath):
                LOGGER.log(f"{filepath}...", end="")
                LOGGER.log("OK", log_type=LogLevel.LOG_SUCCESS, no_date=True)
                os.remove(filepath)

            filepath = f"{build_path}/appspec.yml"
            if os.path.exists(filepath):
                LOGGER.log(f"{filepath}...", end="")
                LOGGER.log("OK", log_type=LogLevel.LOG_SUCCESS, no_date=True)
                os.remove(filepath)

            filepath = f"{build_path}/buildspec.yml"
            if os.path.exists(filepath):
                LOGGER.log(f"{filepath}...", end="")
                LOGGER.log("OK", log_type=LogLevel.LOG_SUCCESS, no_date=True)
                os.remove(filepath)
        LOGGER.log("OK", log_type=LogLevel.LOG_SUCCESS, no_date=True)

        upload_once = True
        for build_target in self.build_targets.values():
            okTemp: int = self.upload_to_epic(app_version=app_version,
                                              build_target=build_target,
                                              simulate=simulate)

            if not okTemp == 0:
                LOGGER.log(" EPIC upload failed, 2nd try...", log_type=LogLevel.LOG_WARNING)
                okTemp = self.upload_to_epic(app_version=app_version,
                                             build_target=build_target,
                                             simulate=simulate)
                if okTemp != 0:
                    return EPIC_CANNOT_UPLOAD

        if not upload_once:
            return errors.STORE_NO_UPLOAD_DONE
        else:
            return ok

    def upload_to_epic(self, build_target: BuildTarget, app_version: str = "", simulate: bool = False) -> int:
        # find the data related to the branch we want to build
        if 'artifact_id' not in build_target.parameters:
            LOGGER.log(f"Buildtarget [{build_target.name}] configuration have no 'artifact_id' parameter",
                       log_type=LogLevel.LOG_ERROR)
            return EPIC_MISSING_PARAMETER

        if 'app_launch' not in build_target.parameters:
            LOGGER.log(f"Buildtarget [{build_target.name}] configuration have no 'app_launch' parameter",
                       log_type=LogLevel.LOG_ERROR)
            return EPIC_MISSING_PARAMETER

        app_args: str = ""
        if 'app_args' in build_target.parameters:
            app_args = build_target.parameters['app_args']

        artifact_id: str = build_target.parameters['artifact_id']
        app_launch: str = build_target.parameters['app_launch']

        # sandbox_id: str = build_target.parameters['sandbox_id']

        build_app_version: str = app_version
        if app_version == "":
            build_app_version = build_target.version

        build_path: str = f'{self.build_path}/{build_target.name}'
        cloud_path: str = f'{self.epic_build_path}/{build_target.name}'

        ok: int = 0
        version_option: str = f' -BuildVersion="{build_app_version}-{build_target.name}"'
        # TODO: if the game project do not manage versions, to it for them
        if not self.check_project_version:
            version_option = ''
        cmd = f'{self.epic_exe_path} -OrganizationId="{self.org_id}" -ProductId="{self.product_id}" -ArtifactId="{artifact_id}" -ClientId="{self.client_id}" -ClientSecret="{self.client_secret}" -mode=UploadBinary -BuildRoot="{build_path}" -CloudDir="{cloud_path}" {version_option} -AppLaunch="{app_launch}" -AppArgs="{app_args}"'

        LOGGER.log("  " + cmd, log_type=LogLevel.LOG_DEBUG)
        LOGGER.log(f" Building Epic {build_target.name} packages...", end="")

        if not simulate:
            ok = os.system(cmd)
        else:
            LOGGER.log("  " + cmd)
            ok = 0

        if ok == 512:
            LOGGER.log(f"Version '{build_app_version}-{build_target.name}' have already been uploaded. Skipping",
                       log_type=LogLevel.LOG_WARNING, no_date=True)
            ok = 0
        elif ok != 0:
            LOGGER.log(f"Executing Epic {self.epic_exe_path} (exitcode={ok})",
                       log_type=LogLevel.LOG_ERROR, no_date=True)
            return ok
        else:
            LOGGER.log("OK", log_type=LogLevel.LOG_SUCCESS, no_date=True)

        return ok
