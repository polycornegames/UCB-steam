import os
import shutil
import stat
from typing import Final

import vdf

from libraries import LOGGER
from libraries.AWS import AWS_S3
from libraries.common import errors
from libraries.common.libraries import replace_in_file, write_in_file
from libraries.logger import LogLevel
from libraries.store import Store

# region ERRORS NUMBER
# must be over 10000
STEAM_CREATE_DIRECTORY1_FAILED: Final[int] = 10701
STEAM_CREATE_DIRECTORY2_FAILED: Final[int] = 10702
STEAM_CREATE_DIRECTORY3_FAILED: Final[int] = 10703
STEAM_CREATE_DIRECTORY4_FAILED: Final[int] = 10704
STEAM_CREATE_DIRECTORY5_FAILED: Final[int] = 10705
STEAM_CREATE_DIRECTORY6_FAILED: Final[int] = 10706
STEAM_INSTALLATION_FAILED: Final[int] = 10707
STEAM_TEST_CONNECTION_FAILED: Final[int] = 10708
STEAM_EXECUTING_FAILED: Final[int] = 10709
STEAM_EXECUTING_APPID_EMPTY: Final[int] = 10710
STEAM_CANNOT_UPLOAD: Final[int] = 10711
STEAM_MISSING_PARAMETER: Final[int] = 10712


# endregion


class Steam(Store):
    def __init__(self, base_path: str, home_path: str, build_path: str, download_path: str, check_project_version: bool,
                 parameters: dict,
                 built: bool = False):
        super().__init__(base_path, home_path, build_path, download_path, check_project_version, parameters, built)
        self.name = "steam"

        if 'steam' not in self.parameters.keys():
            LOGGER.log("Configuration file have no 'steam' section", log_type=LogLevel.LOG_ERROR)
            return

        if 'user' not in self.parameters['steam'].keys():
            LOGGER.log("'steam' configuration file section have no 'user' value", log_type=LogLevel.LOG_ERROR)
            return

        if 'password' not in self.parameters['steam'].keys():
            LOGGER.log("'steam' configuration file section have no 'password' value", log_type=LogLevel.LOG_ERROR)
            return

        self.user: str = self.parameters['steam']['user']
        self.password: str = self.parameters['steam']['password']

        self.drm: bool = False
        self.drm_executable_path: str = ""
        if 'drm' in self.parameters['steam'].keys():
            self.drm = self.parameters['steam']['drm']

            if self.drm and ('drm_executable_path' not in self.parameters['steam'].keys()):
                LOGGER.log("'drm' is set to true however 'steam' configuration file section have no 'drm_executable_path' value",
                           log_type=LogLevel.LOG_ERROR)
                return

            self.drm_executable_path: str = self.parameters['steam']['drm_executable_path']

        self.steam_dir_path: str = f'{base_path}/Steam'
        self.steam_build_path: str = f'{self.steam_dir_path}/build'
        self.steam_scripts_path: str = f'{self.steam_dir_path}/scripts'
        self.steam_exe_path: str = f'{self.steam_dir_path}/steamcmd/steamcmd.sh'

        if 'enabled' in self.parameters[self.name].keys():
            self.enabled = self.parameters[self.name]['enabled']

    def install(self, simulate: bool = False) -> int:
        ok: int = 0
        LOGGER.log("Creating folder structure for Steamworks...", end="")
        if not simulate:
            if not os.path.exists(self.steam_dir_path):
                os.mkdir(self.steam_dir_path)

                if not os.path.exists(self.steam_dir_path):
                    LOGGER.log(f"Error creating directory {self.steam_dir_path} for {self.name}",
                               log_type=LogLevel.LOG_ERROR, no_date=True)
                    return STEAM_CREATE_DIRECTORY1_FAILED
            if not os.path.exists(self.steam_build_path):
                os.mkdir(self.steam_build_path)

                if not os.path.exists(self.steam_build_path):
                    LOGGER.log(f"Error creating directory {self.steam_build_path} for {self.name}",
                               log_type=LogLevel.LOG_ERROR, no_date=True)
                    return STEAM_CREATE_DIRECTORY2_FAILED
            if not os.path.exists(f"{self.steam_dir_path}/output"):
                os.mkdir(f"{self.steam_dir_path}/output")

                if not os.path.exists(f"{self.steam_dir_path}/output"):
                    LOGGER.log(f"Error creating directory {self.steam_dir_path}/output for {self.name}",
                               log_type=LogLevel.LOG_ERROR, no_date=True)
                    return STEAM_CREATE_DIRECTORY3_FAILED
            if not os.path.exists(f"{self.steam_scripts_path}"):
                os.mkdir(f"{self.steam_scripts_path}")

                if not os.path.exists(f"{self.steam_scripts_path}"):
                    LOGGER.log(f"Error creating directory {self.steam_scripts_path} for {self.name}",
                               log_type=LogLevel.LOG_ERROR, no_date=True)
                    return STEAM_CREATE_DIRECTORY4_FAILED
            if not os.path.exists(f"{self.steam_dir_path}/steamcmd"):
                os.mkdir(f"{self.steam_dir_path}/steamcmd")

                if not os.path.exists(f"{self.steam_dir_path}/steamcmd"):
                    LOGGER.log(f"Error creating directory {self.steam_dir_path}/steamcmd for {self.name}",
                               log_type=LogLevel.LOG_ERROR, no_date=True)
                    return STEAM_CREATE_DIRECTORY5_FAILED
            if not os.path.exists(f"{self.steam_dir_path}/steam-sdk"):
                os.mkdir(f"{self.steam_dir_path}/steam-sdk")

                if not os.path.exists(f"{self.steam_dir_path}/steam-sdk"):
                    LOGGER.log(f"Error creating directory {self.steam_dir_path}/steam-sdk for {self.name}",
                               log_type=LogLevel.LOG_ERROR, no_date=True)
                    return STEAM_CREATE_DIRECTORY6_FAILED
            LOGGER.log("OK", log_type=LogLevel.LOG_SUCCESS, no_date=True)
        else:
            LOGGER.log("Skipped", log_type=LogLevel.LOG_SUCCESS, no_date=True)

        LOGGER.log("Downloading Steamworks SDK...", end="")
        if not simulate:
            if not os.path.exists(f"{self.steam_dir_path}/steamcmd/linux32/steamcmd"):
                ok = AWS_S3.s3_download_directory(directory="UCB/steam-sdk",
                                                  destination_path=f"{self.download_path}/steam-sdk")
                if ok != 0:
                    LOGGER.log("Error getting files from S3", log_type=LogLevel.LOG_ERROR, no_date=True)
                    return STEAM_INSTALLATION_FAILED

                shutil.copytree(f"{self.download_path}/steam-sdk/builder_linux", f"{self.steam_dir_path}/steamcmd",
                                dirs_exist_ok=True)
                st = os.stat(self.steam_exe_path)
                os.chmod(self.steam_exe_path, st.st_mode | stat.S_IEXEC)
                st = os.stat(f"{self.steam_dir_path}/steamcmd/linux32/steamcmd")
                os.chmod(f"{self.steam_dir_path}/steamcmd/linux32/steamcmd", st.st_mode | stat.S_IEXEC)
                shutil.rmtree(f"{self.download_path}/steam-sdk")
                LOGGER.log("OK", log_type=LogLevel.LOG_SUCCESS, no_date=True)
            else:
                LOGGER.log("OK (dependencies already met)", log_type=LogLevel.LOG_SUCCESS, no_date=True)
        else:
            LOGGER.log("Skipped", log_type=LogLevel.LOG_SUCCESS, no_date=True)

        return ok

    def test(self) -> int:
        LOGGER.log("Testing Steam connection...", end="")
        ok = os.system(
            f'''{self.steam_exe_path} +login "{self.user}" "{self.password}" +quit''')
        if ok != 0:
            LOGGER.log("Error connecting to Steam", log_type=LogLevel.LOG_ERROR, no_date=True)
            return STEAM_TEST_CONNECTION_FAILED
        LOGGER.log("OK", log_type=LogLevel.LOG_SUCCESS, no_date=True)

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
        okTemp: int = self.upload_to_steam(app_version=app_version,
                                           simulate=simulate, no_live=no_live)

        if not okTemp == 0:
            LOGGER.log(" STEAM upload failed, 2nd try...", log_type=LogLevel.LOG_WARNING)
            okTemp = self.upload_to_steam(app_version=app_version,
                                          simulate=simulate, no_live=no_live)
            if okTemp != 0:
                return STEAM_CANNOT_UPLOAD

        if not upload_once:
            return errors.STORE_NO_UPLOAD_DONE
        else:
            return ok

    def upload_to_steam(self, app_version: str, no_live: bool, simulate: bool) -> int:
        app_id: str = ""
        build_path: str = ""
        first: bool = True

        for build_target in self.build_targets.values():
            # find the data related to the branch we want to build
            if 'depot_id' not in build_target.parameters:
                LOGGER.log(f"Buildtarget [{build_target.name}] configuration have no 'depot_id' parameter", log_type=LogLevel.LOG_ERROR)
                return STEAM_MISSING_PARAMETER

            if 'branch_name' not in build_target.parameters:
                LOGGER.log(f"Buildtarget [{build_target.name}] configuration have no 'branch_name' parameter", log_type=LogLevel.LOG_ERROR)
                return STEAM_MISSING_PARAMETER

            depot_id: str = build_target.parameters['depot_id']
            branch_name: str = build_target.parameters['branch_name']
            live: bool = False
            if not no_live and 'live' in build_target.parameters:
                live = build_target.parameters['live']

            build_path: str = f"{self.build_path}/{build_target.name}"

            build_app_version: str = app_version
            if app_version == "":
                build_app_version = build_target.version

            # now prepare the steam files
            # first time we loop: prepare the main steam file
            if first:
                first = False

                app_id = build_target.parameters['app_id']
                LOGGER.log(f' Preparing main Steam file for app {app_id}...', end="")
                if not simulate:
                    shutil.copyfile(f"{self.steam_scripts_path}/template_app_build.vdf",
                                    f"{self.steam_scripts_path}/app_build_{app_id}.vdf")

                    replace_in_file(f"{self.steam_scripts_path}/app_build_{app_id}.vdf",
                                    "%basepath%", self.base_path)
                    replace_in_file(f"{self.steam_scripts_path}/app_build_{app_id}.vdf",
                                    "%buildpath%", self.steam_build_path)
                    if self.check_project_version:
                        replace_in_file(f"{self.steam_scripts_path}/app_build_{app_id}.vdf",
                                        "%version%", f"v{build_app_version} build")
                    else:
                        replace_in_file(f"{self.steam_scripts_path}/app_build_{app_id}.vdf",
                                        "%version%", "")

                    replace_in_file(f"{self.steam_scripts_path}/app_build_{app_id}.vdf",
                                    "%branch_name%", branch_name)
                    replace_in_file(f"{self.steam_scripts_path}/app_build_{app_id}.vdf",
                                    "%app_id%", app_id)

                    if no_live or not live:
                        replace_in_file(f"{self.steam_scripts_path}/app_build_{app_id}.vdf",
                                        "%live%", "")
                    else:
                        replace_in_file(f"{self.steam_scripts_path}/app_build_{app_id}.vdf",
                                        "%live%", branch_name)

                LOGGER.log("OK", log_type=LogLevel.LOG_SUCCESS, no_date=True)

            # then the depot files
            LOGGER.log(f' Preparing platform Steam file for depot {depot_id} [{build_target.name}]...',
                       end="")
            if not simulate:
                shutil.copyfile(
                    f"{self.steam_scripts_path}/template_depot_build_buildtarget.vdf",
                    f"{self.steam_scripts_path}/depot_build_{build_target.name}.vdf")

                replace_in_file(
                    f"{self.steam_scripts_path}/depot_build_{build_target.name}.vdf",
                    "%depot_id%", depot_id)
                replace_in_file(
                    f"{self.steam_scripts_path}/depot_build_{build_target.name}.vdf",
                    "%buildtargetid%", build_target.name)
                replace_in_file(
                    f"{self.steam_scripts_path}/depot_build_{build_target.name}.vdf",
                    "%buildpath%", self.build_path)
                replace_in_file(
                    f"{self.steam_scripts_path}/depot_build_{build_target.name}.vdf",
                    "%basepath%", self.base_path)

                data = vdf.load(open(f"{self.steam_scripts_path}/app_build_{app_id}.vdf"))
                data['appbuild']['depots'][depot_id] = f"depot_build_{build_target.name}.vdf"

                indented_vdf = vdf.dumps(data, pretty=True)

                write_in_file(f"{self.steam_scripts_path}/app_build_{app_id}.vdf",
                              indented_vdf)

            LOGGER.log("OK", log_type=LogLevel.LOG_SUCCESS, no_date=True)

        LOGGER.log(" Building Steam packages...", end="")
        if app_id != "":
            drm_cmd: str = ""
            if self.drm:
                drm_cmd = f'+drm_wrap {app_id} "{build_path}/{self.drm_executable_path}" "{build_path}/{self.drm_executable_path}" drmtoolp 0'
            cmd = f'{self.steam_exe_path} +login "{self.user}" "{self.password}" {drm_cmd} +run_app_build {self.steam_scripts_path}/app_build_{app_id}.vdf +quit'

            LOGGER.log("  " + cmd, log_type=LogLevel.LOG_DEBUG)

            if not simulate:
                ok = os.system(cmd)
            else:
                ok = 0

            if ok != 0:
                LOGGER.log(f" Executing Steam {self.steam_exe_path} (exitcode={ok})",
                           log_type=LogLevel.LOG_ERROR, no_date=True)
                return ok

            LOGGER.log("OK", log_type=LogLevel.LOG_SUCCESS, no_date=True)
        else:
            LOGGER.log("app_id is empty", log_type=LogLevel.LOG_ERROR, no_date=True)
            return STEAM_EXECUTING_APPID_EMPTY

        return 0
