from typing import Dict

import yaml

from librairies.stores import Store


class Steam(Store):
    def __init__(self, base_path: str, parameters: yaml.Node, built: bool = False):
        super().__init__(base_path, parameters, built)
        self.name = "steam"

        self.user: str = self.parameters['steam']['user']
        self.password: str = self.parameters['steam']['password']

        self.steam_dir_path = f'{base_path}/Steam'
        self.steam_build_path = f'{self.steam_dir_path}/build'
        self.steam_scripts_path = f'{self.steam_dir_path}/scripts'
        self.steam_exe_path = f'{self.steam_dir_path}/steamcmd/steamcmd.sh'

    def build(self, build_target_id: str, app_version: str = "", simulate:bool = False) -> int:
        return 0
