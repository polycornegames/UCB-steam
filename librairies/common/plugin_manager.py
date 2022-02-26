from typing import Dict, Any

from librairies.hook import HookPluginCollection, Hook
from librairies.store import StorePluginCollection, Store


class PluginManager:
    def __init__(self, store_settings: Dict[str, Any], hook_settings: Dict[str, Any], base_path: str, home_path: str, build_path: str, download_path: str):
        self.store_plugins: Dict[str, Store] = dict()
        self.hook_plugins: Dict[str, Hook] = dict()

        self.base_path: str = base_path
        self.home_path: str = home_path
        self.build_path: str = build_path
        self.download_path: str = download_path

        self.store_settings: Dict[str, Any] = store_settings
        self.hook_settings: Dict[str, Any] = hook_settings

        self.load_store_modules()
        self.load_hook_modules()

    def load_store_modules(self):
        store_modules_path = "modules.stores"
        collection: StorePluginCollection = StorePluginCollection(plugin_package=store_modules_path,
                                                                  settings=self.store_settings,
                                                                  base_path=self.base_path,
                                                                  home_path=self.home_path,
                                                                  build_path=self.build_path,
                                                                  download_path=self.download_path)

        for store in collection.plugins:
            self.store_plugins[store.name] = store

    def load_hook_modules(self):
        hook_modules_path = "modules.hooks"
        collection: HookPluginCollection = HookPluginCollection(hook_modules_path,
                                                                settings=self.hook_settings,
                                                                base_path=self.base_path,
                                                                home_path=self.home_path)

        for hook in collection.plugins:
            self.hook_plugins[hook.name] = hook

    def get_store_module(self, store_name: str) -> Store:
        store = None
        if store_name in self.store_plugins.keys():
            store = self.store_plugins[store_name]
        return store

    def get_hook_module(self, hook_name: str) -> Hook:
        hook = None
        if hook_name in self.hook_plugins.keys():
            hook = self.hook_plugins[hook_name]
        return hook
