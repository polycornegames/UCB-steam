from typing import Optional

from librairies import CFG
from librairies.Unity.PolyUCB import PolyUCB

print('UCB module loaded')

UCB: Optional[PolyUCB] = None

if 'unity' in CFG.settings:
    UCB: PolyUCB = PolyUCB(unity_org_id=CFG.settings['unity']['org_id'],
                           unity_project_id=CFG.settings['unity']['project_id'],
                           unity_api_key=CFG.settings['unity']['api_key'])
