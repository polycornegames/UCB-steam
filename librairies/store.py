import importlib
import inspect
import os
import pkgutil
from typing import Dict, List, Any

from librairies import LOGGER
from librairies.Unity.classes import BuildTarget
from librairies.logger import LogLevel


class Store:
    def __init__(self, base_path: str, home_path: str, build_path: str, download_path: str, parameters: dict,
                 built: bool = False):
        self.name: str = "generic"

        self.base_path: str = base_path
        self.home_path: str = home_path
        self.build_path: str = build_path
        self.download_path: str = download_path

        self.built: bool = built
        self.parameters: dict

        if parameters is None:
            self.parameters = dict()
        else:
            self.parameters = parameters
        self.build_targets: Dict[str, BuildTarget] = dict()

    def install(self, simulate: bool = False) -> int:
        raise NotImplementedError

    def test(self) -> int:
        raise NotImplementedError

    def build(self, app_version: str = "", no_live: bool = False, simulate: bool = False, force: bool = False) -> int:
        raise NotImplementedError

    def add_build_target(self, build_target: BuildTarget):
        LOGGER.log(f'  Adding buildtarget {build_target.name} to store {self.name}',
                   log_type=LogLevel.LOG_DEBUG, force_newline=True)
        self.build_targets[build_target.name.lower()] = build_target

    def contains_build_target(self, build_target_id: str) -> bool:
        found = False
        if build_target_id in self.build_targets.keys():
            found = True

        return found

    def get_build_target(self, build_target_id: str) -> BuildTarget:
        build_target = None
        if build_target_id in self.build_targets.keys():
            build_target = self.build_targets[build_target_id]

        return build_target

    def get_build_targets(self) -> List[BuildTarget]:
        build_targets_temp: List[BuildTarget] = list()
        for build_target in self.build_targets.values():
            if build_target not in build_targets_temp:
                build_targets_temp.append(build_target)

        return build_targets_temp


class StorePluginCollection(object):
    """Upon creation, this class will read the plugins package for modules
    that contain a class definition that is inheriting from the Plugin class
    """

    def __init__(self, plugin_package, settings: Dict[str, Any], base_path: str, home_path: str, build_path: str,
                 download_path: str):
        """Constructor that initiates the reading of all available plugins
        when an instance of the PluginCollection object is created
        """
        self.seen_paths = []
        self.plugins: List[Store] = []
        self.plugin_package = plugin_package
        self.base_path: str = base_path
        self.home_path: str = home_path
        self.build_path: str = build_path
        self.download_path: str = download_path
        self.settings: Dict[str, Any] = settings

        self.reload_plugins()

    def reload_plugins(self):
        """Reset the list of all plugins and initiate the walk over the main
        provided plugin package to load all available plugins
        """
        self.plugins = []
        self.seen_paths = []
        # print()
        # print(f'Looking for plugins under package {self.plugin_package}')
        self.walk_package(self.plugin_package)

    def walk_package(self, package):
        """Recursively walk the supplied package to retrieve all plugins
        """
        imported_package = importlib.import_module(package)

        for _, pluginname, ispkg in pkgutil.iter_modules(imported_package.__path__, imported_package.__name__ + '.'):
            if not ispkg:
                plugin_module = __import__(pluginname, fromlist=['blah'])
                clsmembers = inspect.getmembers(plugin_module, inspect.isclass)
                for (_, c) in clsmembers:
                    # Only add classes that are a sub class of Plugin, but NOT Plugin itself
                    if issubclass(c, Store) & (c is not Store):
                        # print(f'    Found plugin class: {c.__module__}.{c.__name__}')
                        test: Store = c(self.base_path, self.home_path, self.build_path, self.download_path,
                                        self.settings)
                        self.plugins.append(test)

        # Now that we have looked at all the modules in the current package, start looking
        # recursively for additional modules in sub packages
        all_current_paths = []
        if isinstance(imported_package.__path__, str):
            all_current_paths.append(imported_package.__path__)
        else:
            all_current_paths.extend([x for x in imported_package.__path__])

        for pkg_path in all_current_paths:
            if pkg_path not in self.seen_paths:
                self.seen_paths.append(pkg_path)

                # Get all sub directory of the current package path directory
                child_pkgs = [p for p in os.listdir(pkg_path) if os.path.isdir(os.path.join(pkg_path, p))]

                # For each sub directory, apply the walk_package method recursively
                for child_pkg in child_pkgs:
                    self.walk_package(package + '.' + child_pkg)
