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
        LOGGER = Logger(CFG.settings['logpath'])
    except IOError:
        code_ok = 10
        print("FATAL ERROR: impossible to create logfile at " + CFG.settings['logpath'])

except IOError:
    code_ok = 11
    print("FATAL ERROR: no configuration file available at " + config_file_path)
    exit()

from librairies.common.plugin_manager import PluginManager

PLUGIN_MANAGER: PluginManager = PluginManager(CFG.settings['stores'], CFG.settings['hooks'],
                                              base_path=CFG.settings['basepath'], home_path=CFG.settings['homepath']
                                              , build_path=CFG.settings['buildpath']
                                              , download_path=CFG.settings['downloadpath'])

from librairies.common.package_manager import PackageManager

PACKAGE_MANAGER: PackageManager = PackageManager(builds_path=CFG.settings['buildpath'],
                                                 download_path=CFG.settings['downloadpath'], build_max_age=180)
