import os

from librairies.config import Config
from librairies.logger import Logger

LOGGER: Logger = None
CFG: Config = None

config_file_path: str = os.path.dirname(os.path.abspath(__file__)) + '/../UCB-steam.config'
try:
    CFG = Config(config_file_path)

    if CFG is None:
        code_ok = 11
        print("FATAL ERROR: no configuration file available at " + config_file_path + '/UCB-steam.config')
        exit()

    try:
        LOGGER = Logger(CFG.settings['logpath'])
    except IOError:
        code_ok = 10
        print("FATAL ERROR: impossible to create logfile at " + CFG.settings['logpath'])

except IOError:
    code_ok = 11
    print("FATAL ERROR: no configuration file available at " + config_file_path + '/UCB-steam.config')
    exit()
