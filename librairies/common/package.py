from typing import Dict, List

from librairies import LOGGER
from librairies.Unity.classes import BuildTarget, Build
from librairies.hook import Hook
from librairies.logger import LogLevel
from librairies.store import Store


class Package:
    def __init__(self, name: str, version: str = "0.0.0", complete: bool = False, downloaded: bool = False,
                 uploaded: bool = False,
                 cleaned: bool = False,
                 notified: bool = False,
                 concerned: bool = False):
        self.name: str = name
        self.version: str = version
        self.stores: Dict[str, Store] = dict()
        self.hooks: Dict[str, Hook] = dict()

        self.downloaded: bool = downloaded
        self.over_max_age: bool = False
        self.must_be_downloaded: bool = False

        self.complete: bool = complete
        self.uploaded: bool = uploaded

        self.cleaned: bool = cleaned

        self.notified: bool = notified

        # if true, means that at least on build is in the UCB list (no matter the status)
        self.concerned: bool = concerned

    def add_hook(self, hook: Hook):
        if hook is not None:
            LOGGER.log(f' Adding hook [{hook.name}] to package [{self.name}]',
                       log_type=LogLevel.LOG_DEBUG, force_newline=True)
            self.hooks[hook.name] = hook

    def add_store(self, store: Store):
        if store is not None:
            LOGGER.log(f' Adding store [{store.name}] to package [{self.name}]',
                       log_type=LogLevel.LOG_DEBUG, force_newline=True)
            self.stores[store.name] = store

    def add_build_target_to_store(self, store_name: str, build_target: BuildTarget):
        self.stores[store_name].add_build_target(build_target)

    def add_build_target_to_hook(self, hook_name: str, build_target: BuildTarget):
        self.hooks[hook_name].add_build_target(build_target)

    def contains_build_target(self, build_target_id: str) -> bool:
        found: bool = False
        for store in self.stores.values():
            if build_target_id in store.contains_build_target(build_target_id=build_target_id):
                found = True

        return found

    def contains_store(self, store_name: str) -> bool:
        found = False
        if store_name in self.stores.keys():
            found = True

        return found

    def contains_hook(self, hook_name: str) -> bool:
        found = False
        if hook_name in self.hooks.keys():
            found = True

        return found

    def get_build_targets(self) -> List[BuildTarget]:
        build_targets_temp: List[BuildTarget] = list()
        for store in self.stores.values():
            for build_target in store.build_targets.values():
                if build_target not in build_targets_temp:
                    build_targets_temp.append(build_target)

        return build_targets_temp

    def get_builds(self) -> List[Build]:
        builds_temp: List[Build] = list()
        for store in self.stores.values():
            for build_target in store.build_targets.values():
                for build in build_target.builds:
                    builds_temp.append(build)

        return builds_temp

    def get_build_targets_for_store(self, store_name: str) -> List[BuildTarget]:
        build_targets_temp: List[BuildTarget] = list()
        if store_name in self.stores.values():
            build_targets_temp = self.stores[store_name].get_build_targets()

        return build_targets_temp

    def get_build_targets_for_hook(self, hook_name: str) -> List[BuildTarget]:
        build_targets_temp: List[BuildTarget] = list()
        if hook_name in self.hooks.values():
            build_targets_temp = self.hooks[hook_name].get_build_targets()

        return build_targets_temp

    def update_completion(self):
        # identify completed builds
        LOGGER.log(f' Updating completion for package: [{self.name}]', log_type=LogLevel.LOG_DEBUG, force_newline=True)

        if len(self.stores) == 0:
            # no stores means... not complete... master of the obvious!
            LOGGER.log(f'  No store in this package', log_type=LogLevel.LOG_DEBUG, force_newline=True)
            self.complete = False
        else:
            for store in self.stores.values():
                if len(store.build_targets) == 0:
                    # no build_target means... not complete... master of the obvious chapter 2!
                    LOGGER.log(f'  No buildtarget for store [{store.name}]', log_type=LogLevel.LOG_DEBUG,
                               force_newline=True)
                    self.complete = False
                    break

                # if we reached this point, then we assume the package is completely built
                self.complete = True

        for store in self.stores.values():
            for build_target in store.build_targets.values():
                # if one of the required build of the package is not complete, then the full package is incomplete
                if not build_target.is_successful():
                    if build_target.build is None:
                        LOGGER.log(f'  Buildtarget [{build_target.name}] for store [{store.name}] has no build',
                                   log_type=LogLevel.LOG_DEBUG, force_newline=True)
                    else:
                        LOGGER.log(
                            f'  Buildtarget [{build_target.name}] for store [{store.name}] not complete ({build_target.build.status})',
                            log_type=LogLevel.LOG_DEBUG, force_newline=True)
                    self.complete = False

    def attach_builds(self, builds: List[Build]):
        for build in builds:
            for store in self.stores.values():
                if build.build_target_id in store.build_targets.keys():
                    self.concerned = True
                    attached: bool = store.build_targets[build.build_target_id].attach_build(build)
                    if attached:
                        LOGGER.log(
                            f'  Attaching build: {build.number}({build.build_target_id}) to store [{store.name}] of package [{self.name}]',
                            log_type=LogLevel.LOG_DEBUG, force_newline=True)
                    else:
                        LOGGER.log(
                            f'  Adding build: {build.number}({build.build_target_id}) to store [{store.name}] of package [{self.name}]',
                            log_type=LogLevel.LOG_DEBUG, force_newline=True)

            for hook in self.hooks.values():
                if build.build_target_id in hook.build_targets.keys():
                    self.concerned = True
                    attached: bool = hook.build_targets[build.build_target_id].attach_build(build)
                    if attached:
                        LOGGER.log(
                            f'  Attaching build: {build.number}({build.build_target_id}) to hook [{hook.name}] of package [{self.name}]',
                            log_type=LogLevel.LOG_DEBUG, force_newline=True)
                    else:
                        LOGGER.log(
                            f'  Adding build: {build.number}({build.build_target_id}) to hook [{hook.name}] of package [{self.name}]',
                            log_type=LogLevel.LOG_DEBUG, force_newline=True)

    def are_all_build_target_valid(self) -> bool:
        for build_target in self.get_build_targets():
            if build_target.is_valid() != 0:
                return False

        return True

    def are_all_build_target_max_age_valid(self) -> bool:
        for build_target in self.get_build_targets():
            if build_target.over_max_age:
                return False

        return True

    def are_all_build_target_cached(self) -> bool:
        for build_target in self.get_build_targets():
            if not build_target.cached:
                return False

        return True


class PackageQueue:
    def __init__(self, ID: str, build_target_id: str, build_number: int, processed: bool):
        self.ID = ID
        self.build_target_id = build_target_id
        self.build_number = build_number
        self.processed = processed
