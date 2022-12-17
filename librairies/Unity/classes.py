from datetime import datetime
from enum import Enum
from typing import Dict, Optional, List

from librairies.common import errors


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
    def __init__(self, number: int, GUID: str, build_target_id: str, status: UCBBuildStatus, date_finished: str,
                 download_link: str, platform: str, last_built_revision: str, UCB_object: Optional[dict] = None):
        self.number: int = number
        self.GUID: str = GUID
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
            self.successful: bool = True
        else:
            self.successful: bool = False
        self.UCB_object: dict = UCB_object


class BuildTarget:
    def __init__(self, name: str, build: Build = None, notified: bool = False):
        self.name: str = name.lower()
        self.build: Optional[Build] = build
        self._builds: List[Build] = list()
        self.notified: bool = notified
        self.parameters: Dict[str, str] = dict()
        self.version = "0.0.0"
        self.processed_stores: Dict[str, bool] = dict()

        self.over_max_age: bool = False
        self.cached: bool = False
        self.downloaded: bool = False
        self.must_be_downloaded: bool = False

        self.cleaned: bool = False
        self.must_be_cleaned: bool = True

    @property
    def builds(self):
        return self._builds

    def process_store(self, store_name: str, success: bool):
        self.processed_stores[store_name] = success

    def is_successful(self) -> bool:
        if self.build is not None and self.build.successful:
            return True

        return False

    def is_valid(self) -> int:
        if self.build is None:
            return errors.UCB_MISSING_BUILD_OBJECT

        if not self.build.successful:
            return errors.UCB_BUILD_IS_NOT_SUCCESSFUL

        if self.build.number == "":
            return errors.UCB_MISSING_BUILD_FIELD_NUMBER

        if self.build.date_finished == datetime.min:
            return errors.UCB_BUILD_IS_FAILED

        if self.build.last_built_revision == "":
            return errors.UCB_MISSING_BUILD_FIELD_LASTBUILTREVISION

        return 0

    def is_cached(self, last_built_revision: str) -> bool:
        if not last_built_revision == "" and last_built_revision == self.build.last_built_revision:
            return True

        return False

    def is_build_date_valid(self, build_max_age: int) -> bool:
        current_date: datetime = datetime.now()
        time_diff = current_date - self.build.date_finished
        time_diff_in_minute: int = int(time_diff.total_seconds() / 60)

        if time_diff_in_minute > build_max_age:
            return False

        return True

    def attach_build(self, build: Build) -> bool:
        ok: bool = False

        if not self._builds.__contains__(build):
            self._builds.append(build)

        if self.build is not None:
            if self.build.number < build.number:
                self.build = build
                ok = True
        else:
            self.build = build
            ok = True

        return ok
