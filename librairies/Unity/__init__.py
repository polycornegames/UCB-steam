from typing import Optional

from librairies import CFG
from librairies.Unity.PolyUCB import PolyUCB

print('UCB module loaded')

UCB: Optional[PolyUCB] = None

if CFG.unity is not None:
    UCB: PolyUCB = PolyUCB(unity_org_id=CFG.unity['org_id'],
                           unity_project_id=CFG.unity['project_id'],
                           unity_api_key=CFG.unity['api_key'])
