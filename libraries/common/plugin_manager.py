from typing import Dict, Any, Optional

from libraries.hook import HookPluginCollection, Hook
from libraries.store import StorePluginCollection, Store


class PluginManager:
    def __init__(self, store_settings: Dict[str, Any], hook_settings: Dict[str, Any], base_path: str, home_path: str,
                 build_path: str, download_path: str, check_project_version: bool):
        self._store_plugins: Dict[str, Store] = dict()
        self._hook_plugins: Dict[str, Hook] = dict()

        self.base_path: str = base_path
        self.home_path: str = home_path
        self.build_path: str = build_path
        self.download_path: str = download_path

        self.check_project_version: bool = check_project_version

        self.store_settings: Dict[str, Any] = store_settings
        self.hook_settings: Dict[str, Any] = hook_settings

        self.store_plugins_collection: Optional[StorePluginCollection] = None
        self.hook_plugins_collection: Optional[HookPluginCollection] = None

        self.load_store_modules()
        self.load_hook_modules()

    @property
    def store_plugins(self):
        return self._store_plugins

    @property
    def hook_plugins(self):
        return self._hook_plugins

    def load_store_modules(self):
        store_modules_path = "modules.stores"
        self.store_plugins_collection = StorePluginCollection(plugin_package=store_modules_path,
                                                              settings=self.store_settings,
                                                              base_path=self.base_path,
                                                              home_path=self.home_path,
                                                              build_path=self.build_path,
                                                              download_path=self.download_path,
                                                              check_project_version=self.check_project_version)

        for store in self.store_plugins_collection.plugins:
            self._store_plugins[store.name] = store

    def load_hook_modules(self):
        hook_modules_path = "modules.hooks"
        self.hook_plugins_collection = HookPluginCollection(hook_modules_path,
                                                            settings=self.hook_settings,
                                                            base_path=self.base_path,
                                                            home_path=self.home_path)

        for hook in self.hook_plugins_collection.plugins:
            self._hook_plugins[hook.name] = hook

    def __get_store_module(self, store_name: str) -> Optional[Store]:
        store: Optional[Store] = None
        if store_name in self._store_plugins.keys():
            store = self._store_plugins[store_name]
        return store

    def __get_hook_module(self, hook_name: str) -> Optional[Hook]:
        hook: Optional[Hook] = None
        if hook_name in self._hook_plugins.keys():
            hook = self._hook_plugins[hook_name]
        return hook

    def get_new_instance_of_store(self, store_name: str) -> Optional[Store]:
        return type(self.__get_store_module(store_name))(self.base_path, self.home_path, self.build_path,
                                                         self.download_path, self.check_project_version, self.store_settings)

    def get_new_instance_of_hook(self, hook_name: str) -> Optional[Hook]:
        return type(self.__get_hook_module(hook_name))(self.base_path, self.home_path, self.hook_settings)
