from typing import Dict

import yaml

from librairies.hook import Hook, HookPluginCollection
from librairies.stores import Store, StorePluginCollection


class Config:
    def __init__(self, config_file_path: str):
        # load the configuration from the config file
        self.config_file_path: str = config_file_path
        self.config_base_path: str = self.config_file_path[:self.config_file_path.index('/')]
        self.store_plugins: Dict[str, Store] = dict()
        self.hook_plugins: Dict[str, Hook] = dict()

        with open(self.config_file_path, "r") as yml_file:
            self.settings: yaml.Node = yaml.load(yml_file, Loader=yaml.FullLoader)

        self.load_store_modules()
        self.load_hook_modules()

    def load_store_modules(self):
        store_modules_path = "modules.stores"
        collection: StorePluginCollection = StorePluginCollection(plugin_package=store_modules_path, settings=self.settings['stores'], base_path=self.settings['basepath'], home_path=self.settings['homepath'])

        for store in collection.plugins:
            self.store_plugins[store.name] = store

    def load_hook_modules(self):
        hook_modules_path = "modules.hooks"
        collection: HookPluginCollection = HookPluginCollection(hook_modules_path, settings=self.settings['hooks'], base_path=self.settings['basepath'], home_path=self.settings['homepath'])

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
