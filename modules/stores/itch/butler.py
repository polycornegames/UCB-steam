import os
import stat
import sys
from typing import Final
from zipfile import ZipFile

import requests

from librairies import LOGGER
from librairies.Unity.classes import BuildTarget
from librairies.common import errors
from librairies.common.libraries import write_in_file
from librairies.logger import LogLevel
from librairies.store import Store

# region ERRORS NUMBER
# must be over 10000
BUTLER_CANNOT_UPLOAD: Final[int] = 10600
BUTLER_CANNOT_DOWNLOAD: Final[int] = 10601
BUTLER_CANNOT_UNZIP: Final[int] = 10602


# endregion


class Itch(Store):
    def __init__(self, base_path: str, home_path: str, build_path: str, download_path: str, check_project_version: bool, parameters: dict,
                 built: bool = False):
        super().__init__(base_path, home_path, build_path, download_path, check_project_version, parameters, built)
        self.name = "butler"

        if 'butler' not in self.parameters.keys():
            LOGGER.log("Configuration file have no 'butler' section", log_type=LogLevel.LOG_ERROR)
            return

        if 'apikey' not in self.parameters['butler'].keys():
            LOGGER.log("'butler' configuration file section have no 'apikey' value", log_type=LogLevel.LOG_ERROR)
            return

        if 'org' not in self.parameters['butler'].keys():
            LOGGER.log("'butler' configuration file section have no 'org' value", log_type=LogLevel.LOG_ERROR)
            return

        if 'project' not in self.parameters['butler'].keys():
            LOGGER.log("'butler' configuration file section have no 'project' value", log_type=LogLevel.LOG_ERROR)
            return

        self.apikey: str = self.parameters['butler']['apikey']
        self.org: str = self.parameters['butler']['org']
        self.project: str = self.parameters['butler']['project']

        self.butler_dir_path: str = f'{base_path}/Butler'

        self.check_project_version = check_project_version

        if sys.platform.startswith('linux'):
            self.butler_exe_path: str = f'{self.butler_dir_path}/butler'
        elif sys.platform.startswith('win32'):
            self.butler_exe_path: str = f'{self.butler_dir_path}/butler.exe'

        self.butler_config_dir_path: str = f'{home_path}/.config/itch'
        self.butler_config_file_path: str = f'{self.butler_config_dir_path}/butler_creds'

    def install(self, simulate: bool = False) -> int:

        LOGGER.log("Creating folder structure for Butler...", end="")
        if not simulate:
            if not os.path.exists(f'{self.home_path}/.config'):
                os.mkdir(f'{self.home_path}/.config')
            if not os.path.exists(self.butler_config_dir_path):
                os.mkdir(self.butler_config_dir_path)

            if not os.path.exists(self.butler_dir_path):
                os.mkdir(self.butler_dir_path)

            LOGGER.log("OK", log_type=LogLevel.LOG_SUCCESS, no_date=True)
        else:
            LOGGER.log("Skipped", log_type=LogLevel.LOG_SUCCESS, no_date=True)

        LOGGER.log("Downloading Butler...", end="")
        if not simulate:
            if not os.path.exists(self.butler_exe_path):
                butler_url = ''
                zip_path = ''
                if sys.platform.startswith('linux'):
                    butler_url = 'https://broth.itch.ovh/butler/linux-amd64/LATEST/archive/default'
                    zip_path = f'{self.butler_dir_path}/butler-linux-amd64.zip'
                elif sys.platform.startswith('win32'):
                    butler_url = 'https://broth.itch.ovh/butler/windows-amd64/LATEST/archive/default'
                    zip_path = f'{self.butler_dir_path}/butler-windows-amd64.zip'

                request = requests.get(butler_url, allow_redirects=True)
                open(zip_path, 'wb').write(request.content)

                if not os.path.exists(zip_path):
                    LOGGER.log("Error downloading Butler", log_type=LogLevel.LOG_ERROR, no_date=True)
                    return BUTLER_CANNOT_DOWNLOAD

                unzipped: bool = False
                try:
                    with ZipFile(zip_path, "r") as zipObj:
                        zipObj.extractall(self.butler_dir_path)
                        unzipped = True
                        LOGGER.log("OK", log_type=LogLevel.LOG_SUCCESS, no_date=True)
                except IOError:
                    unzipped = False

                if not unzipped:
                    LOGGER.log(f'Error unzipping Butler {zip_path} to {self.butler_dir_path}',
                               log_type=LogLevel.LOG_ERROR,
                               no_date=True)
                    return BUTLER_CANNOT_UNZIP

                st = os.stat(self.butler_exe_path)
                os.chmod(self.butler_exe_path, st.st_mode | stat.S_IEXEC)

                LOGGER.log("OK", log_type=LogLevel.LOG_SUCCESS, no_date=True)
            else:
                LOGGER.log("OK (dependencies already met)", log_type=LogLevel.LOG_SUCCESS, no_date=True)
        else:
            LOGGER.log("Skipped", log_type=LogLevel.LOG_SUCCESS, no_date=True)

        LOGGER.log("Setting up Butler...", end="")
        if not simulate:
            write_in_file(self.butler_config_file_path, self.apikey)
            if not os.path.exists(self.butler_config_file_path):
                LOGGER.log("Error setting up Butler", log_type=LogLevel.LOG_ERROR, no_date=True)
                return 25
        LOGGER.log("OK", log_type=LogLevel.LOG_SUCCESS, no_date=True)

        return 0

    def test(self) -> int:
        LOGGER.log("Testing Butler connection...", end="")
        cmd = f'{self.butler_exe_path} status {self.org}/{self.project} 1> nul'
        ok = os.system(cmd)
        if ok != 0:
            LOGGER.log("Error connecting to Butler", log_type=LogLevel.LOG_ERROR, no_date=True)
            return 23
        LOGGER.log("OK", log_type=LogLevel.LOG_SUCCESS, no_date=True)

    def build(self, app_version: str = "", no_live: bool = False, simulate: bool = False, force: bool = False) -> int:
        ok: int = 0
        upload_once: bool = False

        for build_target in self.build_targets.values():
            build_app_version: str = app_version
            if app_version == "":
                build_app_version = build_target.version

            upload_once = True
            okTemp: int = self.upload_to_butler(build_target=build_target, app_version=build_app_version,
                                                simulate=simulate, force_build=force)

            if okTemp == 256:
                LOGGER.log(" BUTLER upload failed, 2nd try...", log_type=LogLevel.LOG_WARNING)
                okTemp = self.upload_to_butler(build_target=build_target, app_version=build_app_version,
                                               simulate=simulate, force_build=force)
                if okTemp != 0:
                    return BUTLER_CANNOT_UPLOAD

        if not upload_once:
            return errors.STORE_NO_UPLOAD_DONE
        else:
            return ok

    def upload_to_butler(self, build_target: BuildTarget, app_version: str = "", simulate: bool = False,
                         force_build: bool = False) -> int:
        build_path: str = f'{self.build_path}/{build_target.name}'

        ok: int = 0
        LOGGER.log(f" Cleaning non necessary files...", end="")
        if not simulate:
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

        LOGGER.log(f" Building itch.io(Butler) {build_target.name} packages...", end="")
        if_used_option: str = " --if-changed"
        if force_build:
            if_used_option = ""
        version_option: str = " --userversion={app_version}"
        if not self.check_project_version:
            version_option = ""
        cmd = f"{self.butler_exe_path} push {build_path} {self.org}/{self.project}:{build_target.parameters['channel']}{version_option}{if_used_option}"
        if not simulate:
            ok = os.system(cmd)
        else:
            ok = 0

        if ok != 0:
            LOGGER.log(f"Executing Butler {self.butler_exe_path} (exitcode={ok})",
                       log_type=LogLevel.LOG_ERROR, no_date=True)
            return ok

        LOGGER.log("OK", log_type=LogLevel.LOG_SUCCESS, no_date=True)

        if simulate:
            LOGGER.log("  " + cmd)

        return ok
