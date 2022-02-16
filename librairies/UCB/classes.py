from datetime import datetime
from enum import Enum
from typing import Dict


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
    number: int
    build_target_id: str
    status: UCBBuildStatus
    date_finished: datetime
    download_link: str
    complete: bool
    platform: str
    last_built_revision: str
    UCB_object: dict

    def __init__(self, number: int, build_target_id: str, status: UCBBuildStatus, date_finished: str,
                 download_link: str, platform: str, last_built_revision: str, UCB_object=None):
        self.number = number
        self.build_target_id = build_target_id
        self.status = status
        if date_finished == "":
            self.date_finished = datetime.min
        else:
            self.date_finished = datetime.strptime(date_finished, "%Y-%m-%dT%H:%M:%S.%fZ")
        self.download_link = download_link
        self.platform = platform
        self.last_built_revision = last_built_revision
        if self.status == UCBBuildStatus.SUCCESS:
            self.complete = True
        else:
            self.complete = False
        self.UCB_object = UCB_object


class BuildTarget:
    name: str
    build: Build
    complete: bool
    parameters: Dict[str, str]

    def __init__(self, name: str, build: Build = None, complete: bool = False):
        self.name = name
        self.build = build
        self.complete = complete
        self.parameters = dict()
