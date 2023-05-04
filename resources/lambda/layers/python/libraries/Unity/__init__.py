__all__ = ['PolyUCB', 'UCB', 'init']

from libraries import CFG, LOGGER
from libraries.Unity.PolyUCB import PolyUCB
from libraries.logger import LogLevel

print('UCB module loaded')

UCB: PolyUCB = PolyUCB()


def init():
    if CFG.unity is not None and len(CFG.unity) > 0:
        if 'org_id' not in CFG.unity:
            LOGGER.log("'unity' configuration file section have no 'org_id' value", log_type=LogLevel.LOG_ERROR)
            return

        if 'project_id' not in CFG.unity:
            LOGGER.log("'unity' configuration file section have no  'project_id' section", log_type=LogLevel.LOG_ERROR)
            return

        if 'api_key' not in CFG.unity:
            LOGGER.log("'unity' configuration file section have no  'api_key' section", log_type=LogLevel.LOG_ERROR)
            return

        UCB.init(unity_org_id=CFG.unity['org_id'],
                 unity_project_id=CFG.unity['project_id'],
                 unity_api_key=CFG.unity['api_key'])
