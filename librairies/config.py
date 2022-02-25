from typing import Dict, Any

import yaml


class Config:
    def __init__(self, config_file_path: str):
        # load the configuration from the config file
        self.config_file_path: str = config_file_path
        self.config_base_path: str = self.config_file_path[:self.config_file_path.index('/')]

        with open(self.config_file_path, "r") as yml_file:
            self.settings: dict = yaml.load(yml_file, Loader=yaml.FullLoader)
