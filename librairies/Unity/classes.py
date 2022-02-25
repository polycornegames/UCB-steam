from datetime import datetime
from enum import Enum
from typing import Dict, Optional


class UCBBuildStatus(Enum):
    SUCCESS = 1
    QUEUED = 2
    SENTTOBUILDER = 3
    STARTED = 4
    RESTARTED = 5
    FAILURE = 6
    CANCELED = 7
    UNKNOWN = 8

    def __str__(self):
        return str(self.name)


class Build:
    def __init__(self, number: int, build_target_id: str, status: UCBBuildStatus, date_finished: str,
                 download_link: str, platform: str, last_built_revision: str, UCB_object: Optional[dict] = None):
        self.number: int = number
        self.build_target_id: str = build_target_id
        self.status: UCBBuildStatus = status
        if date_finished == "":
            self.date_finished: datetime = datetime.min
        else:
            self.date_finished: datetime = datetime.strptime(date_finished, "%Y-%m-%dT%H:%M:%S.%fZ")
        self.download_link: str = download_link
        self.platform: str = platform
        self.last_built_revision: str = last_built_revision
        if self.status == UCBBuildStatus.SUCCESS:
            self.complete: bool = True
        else:
            self.complete: bool = False
        self.UCB_object: dict = UCB_object


class BuildTarget:
    def __init__(self, name: str, build: Build = None, complete: bool = False, notified: bool = False):
        self.name: str = name
        self.build: Optional[Build] = build
        self.complete: bool = complete
        self.notified: bool = notified
        self.parameters: Dict[str, str] = dict()
