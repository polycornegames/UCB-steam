import os
from typing import Optional

from librairies.config import Config
from librairies.logger import Logger

LOGGER: Optional[Logger] = None
CFG: Optional[Config] = None

config_file_path: str = os.path.dirname(os.path.abspath(__file__)) + '/../UCB-steam.config'
try:
    CFG = Config(config_file_path)

    if CFG is None:
        code_ok = 11
        print("FATAL ERROR: no configuration file available at " + config_file_path)
        exit()

    try:
        LOGGER = Logger(CFG.log_path, debug=CFG.debug)
    except IOError:
        code_ok = 10
        print("FATAL ERROR: impossible to create logfile at " + CFG.log_path)

except IOError:
    code_ok = 11
    print("FATAL ERROR: no configuration file available at " + config_file_path)
    exit()

from librairies.common.plugin_manager import PluginManager

PLUGIN_MANAGER: PluginManager = PluginManager(CFG.settings['stores'], CFG.settings['hooks'],
                                              base_path=CFG.base_path, home_path=CFG.home_path,
                                              build_path=CFG.build_path,
                                              download_path=CFG.download_path,
                                              check_project_version=CFG.check_project_version)

from librairies.common.package_manager import PackageManager

PACKAGE_MANAGER: PackageManager = PackageManager(builds_path=CFG.build_path,
                                                 download_path=CFG.download_path,
                                                 check_project_version=CFG.check_project_version,
                                                 build_max_age=CFG.build_max_age)
