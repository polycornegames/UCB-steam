import os
from typing import Dict

import yaml

from librairies import LOGGER
from librairies.UCB.classes import BuildTarget
from librairies.logger import LogLevel
from librairies.stores import Store


class Itch(Store):
    def __init__(self, base_path: str, parameters: yaml.Node, built: bool = False):
        super().__init__(base_path, parameters, built)
        self.name = "butler"

        self.apikey: str = self.parameters['butler']['apikey']
        self.org: str = self.parameters['butler']['org']
        self.project: str = self.parameters['butler']['project']

        self.butler_exe_path = f'{base_path}/Butler/butler'
        self.butler_build_path = f'{base_path}/Steam/build'

    def build(self, build_target: BuildTarget, app_version: str = "", simulate:bool = False) -> int:
        build_path: str = f'{self.butler_build_path}/{build_target.name}'

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
        cmd = f"{self.butler_exe_path} push {build_path} {self.org}/{self.project}:{build_target.parameters['channel']} --userversion={app_version} --if-changed"
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
