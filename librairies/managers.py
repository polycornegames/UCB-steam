from typing import Optional

from librairies.common.package_manager import PackageManager
from librairies.common.plugin_manager import PluginManager


class Managers:

    def __init__(self):
        self.plugin_manager: Optional[PluginManager] = None
        self.package_manager: Optional[PackageManager] = None

    def load_managers(self):
        from librairies import CFG

        self.plugin_manager = PluginManager(CFG.settings['stores'], CFG.settings['hooks'],
                                            base_path=CFG.base_path, home_path=CFG.home_path,
                                            build_path=CFG.build_path,
                                            download_path=CFG.download_path,
                                            check_project_version=CFG.check_project_version)

        self.package_manager = PackageManager(builds_path=CFG.build_path,
                                              download_path=CFG.download_path,
                                              check_project_version=CFG.check_project_version,
                                              clean_uploaded_build=CFG.clean_uploaded_build,
                                              build_max_age=CFG.build_max_age)
