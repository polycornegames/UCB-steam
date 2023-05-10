from datetime import datetime
from enum import Enum
from typing import Dict, Optional, List

from libraries.common import errors


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


class UCBPlatform(Enum):
    UNDEFINED = 0
    WINDOWS = 1
    MACOS = 2
    LINUX = 3

    def __str__(self):
        return str(self.name)

    @staticmethod
    def fromStr(value: str):
        if value == "standalonelinux64":
            return UCBPlatform.LINUX
        elif value == "standaloneosxuniversal":
            return UCBPlatform.MACOS
        elif value == "standalonewindows64":
            return UCBPlatform.WINDOWS
        else:
            return UCBPlatform.UNDEFINED


class Build:
    def __init__(self, number: int, GUID: str, build_target_id: str, status: UCBBuildStatus, date_finished: str,
                 download_link: str, platform: UCBPlatform, last_built_revision: str, UCB_object: Optional[dict] = None,
                 build_queue_id: Optional[str] = None, build_queue_processed: bool = False):
        self.number: int = number
        self.GUID: str = GUID
        self.build_target_id: str = build_target_id
        self.status: UCBBuildStatus = status
        if date_finished == "":
            self.date_finished: datetime = datetime.min
        else:
            self.date_finished: datetime = datetime.strptime(date_finished, "%Y-%m-%dT%H:%M:%S.%fZ")
        self.download_link: str = download_link
        self.platform: UCBPlatform = platform
        self.last_built_revision: str = last_built_revision
        if self.status == UCBBuildStatus.SUCCESS:
            self.successful: bool = True
        else:
            self.successful: bool = False
        self.UCB_object: dict = UCB_object
        self.build_queue_id: Optional[str] = build_queue_id
        self.build_queue_processed: bool = build_queue_processed


class BuildTarget:
    def __init__(self, name: str, build: Build = None, notified: bool = False):
        self.name: str = name.lower()
        self._build: Optional[Build] = build
        self._builds: List[Build] = list()
        self.notified: bool = notified
        self.parameters: Dict[str, str] = dict()
        self.version = "0.0.0"

        self.over_max_age: bool = False
        self.cached: bool = False
        self.must_be_downloaded: bool = False

        self.must_be_cleaned: bool = True

        # status of the build
        self.downloaded: bool = False
        self.downloading: bool = False
        self.uploading: bool = False
        self.uploaded: bool = False
        self.notifying: bool = False
        self.notified: bool = False
        self.cleaning: bool = False
        self.cleaned: bool = False

        self.processed_stores: Dict[str, bool] = dict()
        self.processed_hooks: Dict[str, bool] = dict()

        self.downloaded_file_path: Optional[str] = None

    @property
    def build(self) -> Optional[Build]:
        return self._build

    @property
    def builds(self) -> List[Build]:
        return self._builds

    def process_store(self, store_name: str, success: bool):
        self.processed_stores[store_name] = success

    def process_hook(self, hook_name: str, success: bool):
        self.processed_hooks[hook_name] = success

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

        if self._build is not None:
            if self._build.number < build.number:
                self._build = build
                ok = True
        else:
            self._build = build
            ok = True

        return ok

    def mark_as_downloading(self):
        self.downloading: True
        if self.build and self.build.build_queue_id:
            from libraries.AWS import AWS_DDB
            AWS_DDB.set_build_target_status(self.build.build_queue_id, "downloading")

    def mark_as_downloaded(self):
        self.downloading = False
        self.downloaded = True
        if self.build and self.build.build_queue_id:
            from libraries.AWS import AWS_DDB
            AWS_DDB.set_build_target_status(self.build.build_queue_id, "downloaded")

    def mark_as_uploading(self):
        self.uploading = True
        if self.build and self.build.build_queue_id:
            from libraries.AWS import AWS_DDB
            AWS_DDB.set_build_target_status(self.build.build_queue_id, "uploading")

    def mark_as_uploaded(self):
        self.uploading = False
        self.uploaded = True
        if self.build and self.build.build_queue_id:
            from libraries.AWS import AWS_DDB
            AWS_DDB.set_build_target_status(self.build.build_queue_id, "uploaded")

    def mark_as_notifying(self):
        self.notifying = True
        if self.build and self.build.build_queue_id:
            from libraries.AWS import AWS_DDB
            AWS_DDB.set_build_target_status(self.build.build_queue_id, "notifying")

    def mark_as_notified(self):
        self.notifying = False
        self.notified = True
        if self.build and self.build.build_queue_id:
            from libraries.AWS import AWS_DDB
            AWS_DDB.set_build_target_status(self.build.build_queue_id, "notified")

    def mark_as_cleaning(self):
        self.cleaning = True
        if self.build and self.build.build_queue_id:
            from libraries.AWS import AWS_DDB
            AWS_DDB.set_build_target_status(self.build.build_queue_id, "cleaning")

    def mark_as_cleaned(self):
        self.cleaning = False
        self.cleaned = True
        if self.build and self.build.build_queue_id:
            from libraries.AWS import AWS_DDB
            AWS_DDB.set_build_target_status(self.build.build_queue_id, "cleaned")
