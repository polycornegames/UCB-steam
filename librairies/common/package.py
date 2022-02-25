from typing import Dict, List

from librairies.Unity.classes import BuildTarget, Build, UCBBuildStatus
from librairies.hook import Hook
from librairies.store import Store


class Package:
    def __init__(self, name: str, complete: bool = False, downloaded: bool = False, uploaded: bool = False,
                 cleaned: bool = False,
                 notified: bool = False, concerned: bool = False):
        self.name: str = name
        self.stores: Dict[str, Store] = dict()
        self.hooks: Dict[str, Hook] = dict()
        self.downloaded: bool = downloaded
        self.complete: bool = complete
        self.uploaded: bool = uploaded
        self.cleaned: bool = cleaned
        self.notified: bool = notified
        self.concerned: bool = concerned

    def add_hook(self, hook: Hook):
        if hook is not None:
            self.hooks[hook.name] = hook

    def add_store(self, store: Store):
        if store is not None:
            self.stores[store.name] = store

    def add_build_target_to_store(self, store_name: str, build_target: BuildTarget):
        self.stores[store_name].add_build_target(build_target)

    def add_build_target_to_hook(self, hook_name: str, build_target: BuildTarget):
        self.hooks[hook_name].add_build_target(build_target)

    def contains_build_target(self, build_target_id: str) -> bool:
        found = False
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

    def set_build_target_completion(self, build_target_id: str, complete: bool):
        for store in self.stores.values():
            store.set_build_target_completion(build_target_id, complete)

    def update_completion(self, builds: List[Build]):
        # identify completed builds
        for build in builds:
            self.attach_build(build=build)
            if build.status == UCBBuildStatus.SUCCESS:
                self.set_build_target_completion(build_target_id=build.build_target_id, complete=True)

        if len(self.stores) == 0:
            # no stores means... not complete... master of the obvious!
            self.complete = False
        else:
            for store in self.stores.values():
                if len(store.build_targets) == 0:
                    # no build_target means... not complete... master of the obvious chapter 2!
                    self.complete = False
                    break

                # if we reached this point, then we assume the package is completely built
                self.complete = True

        for store in self.stores.values():
            for build_target_id, build_target in store.build_targets.items():
                # if one of the required build of the package is not complete, then the full package is incomplete
                if not build_target.complete:
                    self.complete = False

    def attach_build(self, build: Build):
        for store in self.stores.values():
            if build.build_target_id in store.build_targets.keys():
                if build.status == UCBBuildStatus.SUCCESS:
                    self.concerned = True
                    if store.build_targets[build.build_target_id].build is not None:
                        if store.build_targets[build.build_target_id].build.number < build.number:
                            store.build_targets[build.build_target_id].build = build
                    else:
                        store.build_targets[build.build_target_id].build = build
                else:
                    if store.build_targets[build.build_target_id].build is None:
                        store.build_targets[build.build_target_id].build = build
