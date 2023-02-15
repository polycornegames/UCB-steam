__all__ = ['CFG', 'LOGGER', 'MANAGERS', 'load']

from pathlib import Path

from libraries.config import Config
from libraries.logger import Logger

CFG: Config = Config()
LOGGER: Logger = Logger()

from libraries.managers import Managers

MANAGERS: Managers = Managers()


def load(config_file_path: str = "", use_config_file: bool = True):
    # the config file is not provided ? use a default one
    if use_config_file and not config_file_path:
        config_file_path = f"{Path(__file__).parent.parent.absolute()}/UCB-steam.config"

    try:
        CFG.load(config_file_path=config_file_path, use_config_file=use_config_file)

        try:
            LOGGER.init(log_file_dir=CFG.log_path, debug=CFG.debug)
        except IOError:
            code_ok = 10
            print("FATAL ERROR: impossible to create logfile at " + CFG.log_path)
    except Exception as e:
        code_ok = 11
        print("FATAL ERROR: " + repr(e))
        exit()
