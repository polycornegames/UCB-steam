import os
from pathlib import Path
from typing import Optional

from librairies.config import Config
from librairies.logger import Logger

LOGGER: Optional[Logger] = None
CFG: Optional[Config] = None

config_file_path: str = f"{Path(__file__).parent.parent.absolute()}/UCB-steam.config"
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

from librairies.managers import Managers
MANAGERS: Managers = Managers()
