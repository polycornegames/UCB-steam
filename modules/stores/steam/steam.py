import os
import shutil
import stat
from typing import Final

import vdf

from librairies import LOGGER
from librairies.AWS import AWS_S3
from librairies.common.libraries import replace_in_file, write_in_file
from librairies.logger import LogLevel
from librairies.store import Store

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
# endregion


class Steam(Store):
    def __init__(self, base_path: str, home_path: str, build_path: str, download_path: str, parameters: dict,
                 built: bool = False):
        super().__init__(base_path, home_path, build_path, download_path, parameters, built)
        self.name = "steam"

        self.user: str = self.parameters['steam']['user']
        self.password: str = self.parameters['steam']['password']

        self.steam_dir_path: str = f'{base_path}/Steam'
        self.steam_build_path: str = f'{self.steam_dir_path}/build'
        self.steam_scripts_path: str = f'{self.steam_dir_path}/scripts'
        self.steam_exe_path: str = f'{self.steam_dir_path}/steamcmd/steamcmd.sh'

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

        return 0

    def test(self) -> int:
        LOGGER.log("Testing Steam connection...", end="")
        ok = os.system(
            f'''{self.steam_exe_path} +login "{self.user}" "{self.password}" +quit''')
        if ok != 0:
            LOGGER.log("Error connecting to Steam", log_type=LogLevel.LOG_ERROR, no_date=True)
            return STEAM_TEST_CONNECTION_FAILED
        LOGGER.log("OK", log_type=LogLevel.LOG_SUCCESS, no_date=True)

        return 0

    def build(self, app_version: str = "", no_live: bool = False, simulate: bool = False) -> int:
        app_id: str = ""
        build_path: str = ""
        first: bool = True

        for build_target in self.build_targets.values():
            # find the data related to the branch we want to build
            depot_id = build_target.parameters['depot_id']
            branch_name = build_target.parameters['branch_name']
            live = build_target.parameters['live']
            build_path = f"{self.build_path}/{build_target.name}"

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
                                    "%basepath%", self.steam_build_path)
                    replace_in_file(f"{self.steam_scripts_path}/app_build_{app_id}.vdf",
                                    "%version%", app_version)
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
            LOGGER.log(f' Preparing platform Steam file for depot {depot_id} / {build_target.name}...',
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
                    "%basepath%", self.base_path)

                data = vdf.load(open(f"{self.steam_scripts_path}/app_build_{app_id}.vdf"))
                data['appbuild']['depots'][depot_id] = f"depot_build_{build_target.name}.vdf"

                indented_vdf = vdf.dumps(data, pretty=True)

                write_in_file(f"{self.steam_scripts_path}/app_build_{app_id}.vdf",
                              indented_vdf)

            LOGGER.log("OK", log_type=LogLevel.LOG_SUCCESS, no_date=True)

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

        LOGGER.log(" Building Steam packages...", end="")
        if app_id != "":
            cmd = f'''{self.steam_exe_path} +login "{self.user}" "{self.password}" +run_app_build {self.steam_scripts_path}/app_build_{app_id}.vdf +quit'''
            if not simulate:
                ok = os.system(cmd)
            else:
                ok = 0

            if ok != 0:
                LOGGER.log(f" Executing the bash file {self.steam_exe_path} (exitcode={ok})",
                           log_type=LogLevel.LOG_ERROR, no_date=True)
                return STEAM_EXECUTING_FAILED

            LOGGER.log("OK", log_type=LogLevel.LOG_SUCCESS, no_date=True)

            if simulate:
                LOGGER.log("  " + cmd)
        else:
            LOGGER.log("app_id is empty", log_type=LogLevel.LOG_ERROR, no_date=True)
            return STEAM_EXECUTING_APPID_EMPTY

        return 0
