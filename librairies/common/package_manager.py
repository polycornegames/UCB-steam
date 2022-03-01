import array
import glob
import os
import shutil
import urllib
from datetime import datetime
from typing import Dict, List
from zipfile import ZipFile

import botocore
from botocore.exceptions import ClientError

from librairies import LOGGER, PLUGIN_MANAGER
from librairies.AWS import AWS_S3, AWS_DDB
from librairies.Unity import UCB
from librairies.Unity.classes import BuildTarget
from librairies.common import errors
from librairies.common.libraries import read_from_file, write_in_file
from librairies.common.package import Package
from librairies.hook import Hook
from librairies.logger import LogLevel
from librairies.store import Store


class PackageManager(object):

    def __init__(self, builds_path: str, download_path: str, build_max_age: int = 180):
        self.packages: Dict[str, Package] = dict()
        self.builds_path: str = builds_path
        self.download_path: str = download_path
        self.build_max_age: int = build_max_age

    def load_config(self, environments: array = None) -> int:
        ok: int = 0

        if environments is None:
            environments = []

        try:
            package_data: list = AWS_DDB.get_packages_data()
        except botocore.exceptions.EndpointConnectionError as e:
            LOGGER.log(e.fmt, log_type=LogLevel.LOG_ERROR, no_date=True)
            return errors.AWS_DDB_CONNECTION_FAILED1
        except ClientError as e:
            LOGGER.log(e.response['Error']['Message'], log_type=LogLevel.LOG_ERROR, no_date=True)
            return errors.AWS_DDB_CONNECTION_FAILED2

        for build_target in package_data:
            LOGGER.log(f'Buildtarget {build_target["id"]}',
                       log_type=LogLevel.LOG_DEBUG, force_newline=True)
            # region STORES
            if 'stores' in build_target:
                for store_name in build_target['stores']:
                    if 'package' in build_target['stores'][store_name]:
                        package_name: str = build_target['stores'][store_name]['package']

                        # filter only on wanted packages (see arguments)
                        wanted_package: bool = False
                        if len(environments) == 0:
                            wanted_package = True
                        else:
                            for environment in environments:
                                if package_name == environment:
                                    wanted_package = True
                                    break

                        if wanted_package:
                            # package is not already part of the list ? create it
                            if package_name not in self.packages.keys():
                                package = Package(name=package_name)
                                self.packages[package_name] = package
                            else:
                                package = self.packages[package_name]

                            # store is not already part of the package list ? add it
                            store_exists: bool = True
                            if not package.contains_store(store_name):
                                store: Store = PLUGIN_MANAGER.get_new_instance_of_store(store_name)
                                if store is not None:
                                    package.add_store(store)
                                else:
                                    store_exists = False

                            # if the store plugin exists, continue
                            if store_exists:
                                # region BuildTarget creation
                                build_target_obj = BuildTarget(name=build_target['id'])
                                for parameter, value in build_target['stores'][store_name].items():
                                    if parameter != 'package':
                                        build_target_obj.parameters[parameter] = value
                                # endregion

                                self.packages[package_name].add_build_target_to_store(store_name, build_target_obj)
                            else:
                                LOGGER.log(f'Store plugin {store_name} does not exists', log_type=LogLevel.LOG_WARNING)
            # endregion

            # region HOOKS
            if 'hooks' in build_target:
                for hook_name in build_target['hooks']:
                    if 'package' in build_target['hooks'][hook_name]:
                        package_name = build_target['hooks'][hook_name]['package']

                        # filter only on wanted packages (see arguments)
                        wanted_package: bool = False
                        if len(environments) == 0:
                            wanted_package = True
                        else:
                            for environment in environments:
                                if package_name == environment:
                                    wanted_package = True
                                    break

                        if wanted_package:
                            # package is not already part of the list ? create it
                            if package_name not in self.packages:
                                package = Package(name=package_name)
                                self.packages[package_name] = package
                            else:
                                package = self.packages[package_name]

                            # hook is not already part of the package list ? add it
                            hook_exists: bool = True
                            if not package.contains_hook(hook_name):
                                hook: Hook = PLUGIN_MANAGER.get_new_instance_of_hook(hook_name)
                                if hook is not None:
                                    package.add_hook(hook)
                                else:
                                    hook_exists = False

                            # if the hook plugin exists, continue
                            if hook_exists:
                                # region BuildTarget creation
                                build_target_obj = BuildTarget(name=build_target['id'])
                                for parameter, value in build_target['hooks'][hook_name].items():
                                    if parameter != 'package':
                                        build_target_obj.parameters[parameter] = value
                                # endregion

                                self.packages[package_name].add_build_target_to_hook(hook_name,
                                                                                     build_target_obj)
                            else:
                                LOGGER.log(f'Hook plugin {hook_name} does not exists', log_type=LogLevel.LOG_WARNING)
            # endregion

        for package in self.packages.values():
            self.packages[package.name].stores = dict(sorted(package.stores.items()))
            self.packages[package.name].hooks = dict(sorted(package.hooks.items()))

        return ok

    def get_version(self, force: bool = False, app_version: str = "") -> int:
        ok: int = 0
        faulty: bool = False

        LOGGER.log("Getting version...")
        already_versioned_build_targets: Dict[str, str] = dict()
        for package in self.packages.values():
            LOGGER.log(f' Package: {package.name}', log_type=LogLevel.LOG_DEBUG, end="")
            if package.complete or force:
                if not package.complete:
                    faulty = True
                    LOGGER.log(" Process forced to continue (any force flag used)",
                               log_type=LogLevel.LOG_WARNING)

                LOGGER.log(f' (complete)', log_type=LogLevel.LOG_DEBUG, no_date=True)
                build_targets = package.get_build_targets()
                for build_target in build_targets:
                    LOGGER.log(f'  {build_target.name}', log_type=LogLevel.LOG_DEBUG)
                    if build_target.name in already_versioned_build_targets.keys():
                        build_target.version = already_versioned_build_targets[build_target.name]
                    else:
                        build_os_path = f"{self.builds_path}/{build_target.name}"
                        if app_version == "":
                            LOGGER.log(f' Getting the version of the buildtarget {build_target.name} from files...',
                                       end="")
                            pathFileVersion = glob.glob(build_os_path + "/**/UCB_version.txt", recursive=True)

                            if len(pathFileVersion) == 1:
                                if os.path.exists(pathFileVersion[0]):
                                    version: str = read_from_file(pathFileVersion[0])
                                    version = version.rstrip('\n')
                                    # if not simulate:
                                    #    os.remove(pathFileVersion[0])

                                    build_target.version = version
                                    package.version = version

                                    # let's make sure that we'll not extract the version twice
                                    already_versioned_build_targets[build_target.name] = version

                                    LOGGER.log(" " + version + " ", log_type=LogLevel.LOG_INFO,
                                               no_date=True,
                                               end="")
                                    LOGGER.log("OK ", log_type=LogLevel.LOG_SUCCESS, no_date=True)
                            else:
                                LOGGER.log(
                                    f"File version UCB_version.txt was not found in build directory {build_os_path}",
                                    log_type=LogLevel.LOG_WARNING, no_date=True)
                                return errors.VERSION_FILE_NOT_FOUND
                        else:
                            build_target.version = app_version
                            package.version = app_version
                            LOGGER.log(' Getting the version of the build from argument...', end="")
                            LOGGER.log(" " + app_version + " ", log_type=LogLevel.LOG_INFO, no_date=True,
                                       end="")
                            LOGGER.log("OK ", log_type=LogLevel.LOG_SUCCESS, no_date=True)
            else:
                LOGGER.log(f' (incomplete)', log_type=LogLevel.LOG_DEBUG, no_date=True)

        return ok

    def download_builds(self, force: bool = False, simulate: bool = False, no_s3upload: bool = False) -> int:
        ok: int = 0
        faulty: bool = False

        LOGGER.log("Downloading build from UCB...")
        already_downloaded_build_targets: List[str] = list()
        for package in self.packages.values():
            if package.complete:
                build_targets = package.get_build_targets()
                for build_target in build_targets:
                    if build_target.build.complete:
                        if not already_downloaded_build_targets.__contains__(build_target.name):
                            # store the data necessary for the next steps
                            build_os_path = f"{self.builds_path}/{build_target.name}"
                            last_built_revision_path = f"{self.builds_path}/{build_target.name}_lastbuiltrevision.txt"
                            last_built_revision: str = ""
                            if os.path.exists(last_built_revision_path):
                                last_built_revision = read_from_file(last_built_revision_path)

                            if build_target.build is None:
                                LOGGER.log(" Missing build object", log_type=LogLevel.LOG_ERROR)
                                return errors.UCB_MISSING_BUILD_OBJECT

                            LOGGER.log(f" Preparing {build_target.name}")
                            if build_target.build.number == "":
                                LOGGER.log(" Missing builds field", log_type=LogLevel.LOG_ERROR, no_date=True)
                                return errors.UCB_MISSING_BUILD_FIELD_NUMBER

                            if build_target.build.date_finished == datetime.min:
                                LOGGER.log(" The build seems to be a failed one", log_type=LogLevel.LOG_ERROR,
                                           no_date=True)
                                return errors.UCB_BUILD_IS_FAILED

                            if build_target.build.last_built_revision == "":
                                LOGGER.log(" Missing builds field", log_type=LogLevel.LOG_ERROR, no_date=True)
                                return errors.UCB_MISSING_BUILD_FIELD_LASTBUILTREVISION

                            # continue if this build file was not downloaded during the previous run
                            if not last_built_revision == "" and last_built_revision == build_target.build.last_built_revision:
                                LOGGER.log(f"  Skipping... (already been downloaded during a previous run)")
                            else:
                                current_date = datetime.now()
                                time_diff = current_date - build_target.build.date_finished
                                time_diff_in_minute = int(time_diff.total_seconds() / 60)
                                LOGGER.log(
                                    f"  Continuing with build #{build_target.build.number} for {build_target.name} finished {time_diff_in_minute} minutes ago...",
                                    end="")
                                if time_diff_in_minute > self.build_max_age:
                                    if force:
                                        faulty = True
                                        LOGGER.log(" Process forced to continue (--force flag used)",
                                                   log_type=LogLevel.LOG_WARNING)
                                    else:
                                        LOGGER.log(
                                            f" The build is too old (max {str(self.build_max_age)} min). Try using --force",
                                            log_type=LogLevel.LOG_ERROR,
                                            no_date=True)
                                        return errors.UCB_BUILD_TOO_OLD
                                else:
                                    LOGGER.log(f"OK", log_type=LogLevel.LOG_SUCCESS, no_date=True)

                                zipfile = f"{self.download_path}/ucb{build_target.name}.zip"

                                LOGGER.log(f"  Deleting old files in {build_os_path}...", end="")
                                if not simulate:
                                    if os.path.exists(zipfile):
                                        os.remove(zipfile)
                                    if os.path.exists(build_os_path):
                                        shutil.rmtree(build_os_path, ignore_errors=True)
                                LOGGER.log("OK", log_type=LogLevel.LOG_SUCCESS, no_date=True)

                                LOGGER.log(f'  Downloading the built zip file {zipfile}...', end="")
                                if not simulate:
                                    urllib.request.urlretrieve(build_target.build.download_link, zipfile)
                                LOGGER.log("OK", log_type=LogLevel.LOG_SUCCESS, no_date=True)

                                # store the lastbuiltrevision in a txt file for diff check
                                if not simulate:
                                    if os.path.exists(last_built_revision_path):
                                        os.remove(last_built_revision_path)
                                    write_in_file(last_built_revision_path,
                                                  build_target.build.last_built_revision)

                                LOGGER.log(f'  Extracting the zip file in {build_os_path}...', end="")
                                if not simulate:
                                    unzipped: bool = False
                                    try:
                                        with ZipFile(zipfile, "r") as zipObj:
                                            zipObj.extractall(build_os_path)
                                            unzipped = True
                                            LOGGER.log("OK", log_type=LogLevel.LOG_SUCCESS, no_date=True)
                                    except IOError:
                                        unzipped = False

                                    if not unzipped:
                                        LOGGER.log(f'Error unzipping {zipfile} to {build_os_path}',
                                                   log_type=LogLevel.LOG_ERROR,
                                                   no_date=True)
                                        return errors.UCB_CANNOT_UNZIP
                                else:
                                    LOGGER.log("OK", log_type=LogLevel.LOG_SUCCESS, no_date=True)

                                if not no_s3upload:
                                    s3path = f'UCB/UCB-builds/{package.name}/ucb{build_target.name}.zip'
                                    LOGGER.log(f'  Uploading copy to S3 {s3path} ...', end="")
                                    if not simulate:
                                        ok = AWS_S3.s3_upload_file(zipfile, s3path)
                                    else:
                                        ok = 0

                                    if ok != 0:
                                        LOGGER.log(
                                            f'Error uploading file "ucb{build_target.name}.zip" to AWS {s3path}. Check the IAM permissions',
                                            log_type=LogLevel.LOG_ERROR, no_date=True)
                                        return errors.UCB_CANNOT_UPLOAD_TO_S3
                                    LOGGER.log("OK", log_type=LogLevel.LOG_SUCCESS, no_date=True)

                            # let's make sure that we'll not download the zip file twice
                            already_downloaded_build_targets.append(build_target.name)

                # set the package as downloaded if the process was not faulty
                # we could reach this point even with error because of force parameter
                if not faulty:
                    package.downloaded = True

        return ok

    def upload_builds(self, stores: List[str], app_version: str = "", no_live: bool = False,
                      force: bool = False, simulate: bool = False) -> int:
        ok: int = 0
        faulty: bool = False

        for package in self.packages.values():
            # we only want to build the packages that are complete and filter on wanted one (see arguments)
            if package.complete or force:
                if not package.complete:
                    faulty = True
                    LOGGER.log(" Process forced to continue (any force flag used)",
                               log_type=LogLevel.LOG_WARNING)

                for store in package.stores.values():
                    LOGGER.log(f'Starting {store.name} process for package {package.name}...')
                    if len(stores) == 0 or stores.__contains__(store.name):
                        okTemp: int = store.build(app_version=app_version, no_live=no_live, simulate=simulate)

                        if okTemp != 0:
                            for buildtarget in store.build_targets.values():
                                buildtarget.process_store(store.name, False)
                            faulty = True
                            LOGGER.log(
                                f'Error during upload (error code={okTemp})',
                                log_type=LogLevel.LOG_ERROR, no_date=True)
                            return okTemp
                        else:
                            for buildtarget in store.build_targets.values():
                                buildtarget.process_store(store.name, True)

                if not faulty:
                    package.uploaded = True

            else:
                if package.concerned:
                    LOGGER.log(f' Package {package.name} is not complete and will not be processed for stores...',
                               log_type=LogLevel.LOG_WARNING)
        return ok

    def clean_builds(self, force: bool = False, simulate: bool = False) -> int:
        ok: int = 0
        faulty: bool = False

        already_cleaned_build_targets: List[str] = list()
        # let's remove the build successfully uploaded to Steam or Butler from UCB
        # clean only the packages that are successful
        for package in self.packages.values():
            if (package.complete and package.uploaded) or force:
                if not package.complete or not package.uploaded:
                    faulty = True
                    LOGGER.log(" Process forced to continue (any force flag used)",
                               log_type=LogLevel.LOG_WARNING)

                LOGGER.log(f" Cleaning package {package.name}...")
                build_targets = package.get_build_targets()
                cleaned = True

                for build_target in build_targets:
                    if not already_cleaned_build_targets.__contains__(build_target.name):
                        # cleanup everything related to this package
                        for build in UCB.builds_categorized['success'] + \
                                     UCB.builds_categorized['failure'] + \
                                     UCB.builds_categorized['canceled']:
                            if build.build_target_id == build_target.name:
                                LOGGER.log(
                                    f"  Deleting build #{build.number} for buildtarget {build_target.name} (status: {build.status})...",
                                    end="")
                                if not simulate:
                                    if not UCB.delete_build(build_target.name, build.number):
                                        cleaned = False
                                LOGGER.log("OK", log_type=LogLevel.LOG_SUCCESS, no_date=True)

                                # let's make sure that we'll not cleanup the zip file twice
                                already_cleaned_build_targets.append(build_target.name)

                if not faulty:
                    package.cleaned = cleaned

            else:
                if package.concerned:
                    LOGGER.log(f' Package {package.name} is not built and will not be cleaned...',
                               log_type=LogLevel.LOG_WARNING)

        # additional cleaning steps
        LOGGER.log(f"  Deleting additional files...", end="")

        LOGGER.log("OK", log_type=LogLevel.LOG_SUCCESS, no_date=True)

        return ok

    def notify(self, hooks: List[str], force: bool = False, simulate: bool = False) -> int:
        ok: int = 0
        faulty: bool = False

        already_notified_build_targets: List[str] = list()
        for package in self.packages.values():
            # we only want to build the packages that are complete and filter on wanted one (see arguments)
            if (package.complete and package.uploaded and package.cleaned) or force:
                if not package.complete or not package.uploaded or not package.cleaned:
                    faulty = True
                    LOGGER.log(" Process forced to continue (any force flag used)",
                               log_type=LogLevel.LOG_WARNING)

                LOGGER.log(f" Notifying package {package.name}...")
                for hook in package.hooks.values():
                    if len(hooks) == 0 or hooks.__contains__(hook.name):
                        for build_target in hook.build_targets.values():
                            if not already_notified_build_targets.__contains__(build_target.name):
                                okTemp: int = hook.notify(build_target=build_target, simulate=simulate)

                                if okTemp != 0:
                                    LOGGER.log(
                                        f'Error during notification (error code={okTemp})',
                                        log_type=LogLevel.LOG_ERROR, no_date=True)
                                    return okTemp

                                if not faulty:
                                    package.notified = True

            else:
                if package.concerned:
                    LOGGER.log(f' Package {package.name} is not built and will not be notified by hooks...',
                               log_type=LogLevel.LOG_WARNING)
        return ok

    def print_config(self, with_diag: bool = False):
        for package_name, package in self.packages.items():
            LOGGER.log(f'name: {package_name}', no_date=True)
            # LOGGER.log(f'version: {package.version}', no_date=True)

            if with_diag:
                LOGGER.log(f'  concerned: ', no_date=True, end="")
                if package.concerned:
                    LOGGER.log('YES', no_date=True, log_type=LogLevel.LOG_SUCCESS)
                else:
                    LOGGER.log('NO', no_date=True, no_prefix=True, log_type=LogLevel.LOG_WARNING)

                LOGGER.log(f'  complete: ', no_date=True, end="")
                if package.complete:
                    LOGGER.log('YES', no_date=True, log_type=LogLevel.LOG_SUCCESS)
                else:
                    if package.concerned:
                        LOGGER.log('NO', no_date=True, no_prefix=True, log_type=LogLevel.LOG_ERROR)
                    else:
                        LOGGER.log('NO (not concerned)', no_date=True, log_type=LogLevel.LOG_WARNING, no_prefix=True)

            for store in package.stores.values():
                LOGGER.log(f'  store: {store.name}', no_date=True)
                for build_target in store.build_targets.values():
                    LOGGER.log(f'    buildtarget: {build_target.name}', no_date=True)
                    if with_diag:
                        LOGGER.log(f'      complete: ', no_date=True, end="")
                        if build_target.complete:
                            LOGGER.log('YES', no_date=True, log_type=LogLevel.LOG_SUCCESS)
                        else:
                            if package.concerned:
                                LOGGER.log('NO', no_date=True, no_prefix=True, log_type=LogLevel.LOG_ERROR)
                            else:
                                LOGGER.log('NO (not concerned)', no_date=True, log_type=LogLevel.LOG_WARNING,
                                           no_prefix=True)

                    for key, value in build_target.parameters.items():
                        LOGGER.log(f'      {key}: {value}', no_date=True)

                    if with_diag:
                        if build_target.build:
                            LOGGER.log(f'      builds: #{build_target.build.number} ({build_target.build.status})',
                                       no_date=True)
                            LOGGER.log(f'        complete: ', no_date=True, end="")
                            if build_target.build.complete:
                                LOGGER.log('YES', no_date=True, log_type=LogLevel.LOG_SUCCESS)
                            else:
                                if package.concerned:
                                    LOGGER.log('NO', no_date=True, no_prefix=True, log_type=LogLevel.LOG_ERROR)
                                else:
                                    LOGGER.log('NO (not concerned)', no_date=True, log_type=LogLevel.LOG_WARNING,
                                               no_prefix=True)

            for hook in package.hooks.values():
                LOGGER.log(f'  hook: {hook.name}', no_date=True)
                for build_target in hook.build_targets.values():
                    LOGGER.log(f'    buildtarget: {build_target.name}', no_date=True)
                    if with_diag:
                        LOGGER.log(f'      complete: ', no_date=True, end="")
                        if build_target.complete:
                            LOGGER.log('YES', no_date=True, log_type=LogLevel.LOG_SUCCESS)
                        else:
                            if package.concerned:
                                LOGGER.log('NO', no_date=True, no_prefix=True, log_type=LogLevel.LOG_ERROR)
                            else:
                                LOGGER.log('NO (not concerned)', no_date=True, log_type=LogLevel.LOG_WARNING,
                                           no_prefix=True)

                    for key, value in build_target.parameters.items():
                        LOGGER.log(f'      {key}: {value}', no_date=True)

            LOGGER.log('', no_date=True)
