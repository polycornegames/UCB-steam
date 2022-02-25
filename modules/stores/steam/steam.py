import os
import shutil
import stat

import yaml

from librairies import LOGGER
from librairies.AWS import AWS_S3
from librairies.Unity.classes import BuildTarget
from librairies.logger import LogLevel
from librairies.store import Store


class Steam(Store):
    def __init__(self, base_path: str, home_path: str, build_path: str, download_path: str, parameters: dict, built: bool = False):
        super().__init__(base_path, home_path, build_path, download_path, parameters, built)
        self.name = "steam"

        self.user: str = self.parameters['steam']['user']
        self.password: str = self.parameters['steam']['password']

        self.steam_dir_path: str = f'{base_path}/Steam'
        self.steam_build_path: str = f'{self.steam_dir_path}/build'
        self.steam_scripts_path: str = f'{self.steam_dir_path}/scripts'
        self.steam_exe_path: str = f'{self.steam_dir_path}/steamcmd/steamcmd.sh'

    def install(self, simulate: bool = False) -> int:
        LOGGER.log("Creating folder structure for Steamworks...", end="")
        if not simulate:
            if not os.path.exists(self.steam_dir_path):
                os.mkdir(self.steam_dir_path)
            if not os.path.exists(self.steam_build_path):
                os.mkdir(self.steam_build_path)
            if not os.path.exists(f"{self.steam_dir_path}/output"):
                os.mkdir(f"{self.steam_dir_path}/output")
            if not os.path.exists(f"{self.steam_dir_path}/scripts"):
                os.mkdir(f"{self.steam_scripts_path}")
            if not os.path.exists(f"{self.steam_dir_path}/steamcmd"):
                os.mkdir(f"{self.steam_dir_path}/steamcmd")
            if not os.path.exists(f"{self.steam_dir_path}/steam-sdk"):
                os.mkdir(f"{self.steam_dir_path}/steam-sdk")
            LOGGER.log("OK", log_type=LogLevel.LOG_SUCCESS, no_date=True)
        else:
            LOGGER.log("Skipped", log_type=LogLevel.LOG_SUCCESS, no_date=True)

        LOGGER.log("Downloading Steamworks SDK...", end="")
        if not simulate:
            if not os.path.exists(f"{self.steam_dir_path}/steamcmd/linux32/steamcmd"):
                ok = AWS_S3.s3_download_directory(directory="Unity/steam-sdk",
                                                  destination_path=f"{self.download_path}/steam-sdk")
                if ok != 0:
                    LOGGER.log("Error getting files from S3", log_type=LogLevel.LOG_ERROR, no_date=True)
                    return 22

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
            return 23
        LOGGER.log("OK", log_type=LogLevel.LOG_SUCCESS, no_date=True)

        return 0

    def build(self, build_target: BuildTarget, app_version: str = "", simulate: bool = False) -> int:
        return 0
