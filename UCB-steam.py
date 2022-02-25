__version__ = "0.31"

import array
import getopt
import glob
import os
import shutil
import sys
import time
from typing import Dict, List

import vdf

from librairies import LOGGER, CFG, PACKAGE_MANAGER, PLUGIN_MANAGER
from librairies.AWS.aws import PolyAWSS3, PolyAWSDynamoDB, PolyAWSSES
from librairies.Unity import UCB
from librairies.Unity.classes import Build
from librairies.common.libraries import write_in_file, replace_in_file, read_from_file
from librairies.common.package import Package
from librairies.logger import LogLevel

start_time = time.time()


# region HELPER LIBRARY
def print_help():
    print(
        f"Unity-steam.py [--platform=(standalonelinux64, standaloneosxuniversal, standalonewindows64)] [--environment=(environment1, environment2, ...)] [--store=(store1,store2,...)] [--nolive] [--force] [--version=<version>] [--install] [--nodownload] [--nos3upload] [--noupload] [--noclean] [--noshutdown] [--noemail] [--simulate] [--showconfig | --showdiag] [--steamuser=<steamuser>] [--steampassword=<steampassword>]")


def print_config(packages: Dict[str, Package], with_diag: bool = False):
    for package_name, package in packages.items():
        LOGGER.log(f'name: {package_name}', no_date=True)

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

        LOGGER.log('', no_date=True)


# endregion

class StoreType:
    pass


class HookType:
    pass


def main(argv):
    LOGGER.log("Settings environment variables...", end="")
    LOGGER.log("OK", log_type=LogLevel.LOG_SUCCESS, no_date=True)

    steam_appversion = ""

    platform = ""
    stores: array = []
    hooks: array = []
    environments: array = []
    no_download = False
    no_s3upload = True
    no_upload = False
    no_clean = False
    force = False
    install = False
    show_config = False
    show_diag = False
    no_live = False
    simulate = False

    # region ARGUMENTS CHECK
    try:
        options, arguments = getopt.getopt(argv, "hldocsfip:lv:t:u:a:",
                                           ["help", "nolive", "nodownload", "nos3upload", "noupload", "noclean",
                                            "noshutdown",
                                            "noemail",
                                            "force", "install", "simulate", "showconfig", "showdiag", "platform=",
                                            "store=",
                                            "environment=",
                                            "version=",
                                            "steamuser=",
                                            "steampassword="])
    except getopt.GetoptError:
        LOGGER.log(log_type=LogLevel.LOG_ERROR, message=f'parameter error: {getopt.GetoptError.msg}')
        print()
        return 10

    for option, argument in options:
        if option in ("-h", "--help"):
            print_help()
            return 10
        elif option in ("-p", "--platform"):
            if argument != "standalonelinux64" and argument != "standaloneosxuniversal" and argument != "standalonewindows64":
                LOGGER.log(log_type=LogLevel.LOG_ERROR,
                           message="parameter --platform takes only standalonelinux64, standaloneosxuniversal or standalonewindows64 as valid value")
                print_help()
                return 10
            platform = argument
        elif option == "--store":
            stores = argument.split(',')
            if len(stores) == 0:
                LOGGER.log(log_type=LogLevel.LOG_ERROR, message="parameter --store must have at least one value")
                print_help()
                return 10
        elif option == "--environment":
            environments = argument.split(',')
            if len(environments) == 0:
                LOGGER.log(log_type=LogLevel.LOG_ERROR, message="parameter --environment must have at least one value")
                print_help()
                return 10
        elif option in ("-i", "--install"):
            no_download = True
            no_upload = True
            no_clean = True
            install = True
        elif option in ("-d", "--nodownload"):
            no_download = True
        elif option in ("-d", "--nos3upload"):
            no_s3upload = True
        elif option in ("-d", "--noupload"):
            no_upload = True
        elif option in ("-d", "--noclean"):
            no_clean = True
        elif option in ("-f", "--force"):
            force = True
        elif option in ("-f", "--simulate"):
            simulate = True
        elif option == "--showconfig":
            show_config = True
        elif option == "--showdiag":
            show_diag = True
        elif option in ("-l", "--live"):
            no_live = True
        elif option in ("-v", "--version"):
            steam_appversion = argument
        elif option in ("-u", "--steamuser"):
            CFG.settings['steam']['user'] = argument
        elif option in ("-a", "--steampassword"):
            CFG.settings['steam']['password'] = argument

    # endregion

    # region INSTALL
    # install all the dependencies and test them
    if install:
        LOGGER.log("Updating apt sources...", end="")
        if not simulate:
            if sys.platform.startswith('linux'):
                ok = os.system("sudo apt-get update -qq -y > /dev/null 1")
                if ok > 0:
                    LOGGER.log("Dependencies installation failed", log_type=LogLevel.LOG_ERROR, no_date=True)
                    return 210
                LOGGER.log("OK", log_type=LogLevel.LOG_SUCCESS, no_date=True)
            else:
                LOGGER.log("OS is not Linux", log_type=LogLevel.LOG_SUCCESS, no_date=True)
        else:
            LOGGER.log("Skipped", log_type=LogLevel.LOG_SUCCESS, no_date=True)

        LOGGER.log("Installing dependencies...", end="")
        if not simulate:
            if sys.platform.startswith('linux'):
                ok = os.system("sudo apt-get install -qq -y mc python3-pip git lib32gcc1 python3-requests > /dev/null")
                if ok > 0:
                    LOGGER.log("Dependencies installation failed", log_type=LogLevel.LOG_ERROR, no_date=True)
                    return 211
                LOGGER.log("OK", log_type=LogLevel.LOG_SUCCESS, no_date=True)
            elif sys.platform.startswith('win32'):
                ok = os.system("python.exe -m pip install --upgrade pip --no-warn-script-location 1> nul")
                if ok > 0:
                    LOGGER.log("Dependencies installation failed", log_type=LogLevel.LOG_ERROR, no_date=True)
                    return 211
                LOGGER.log("OK", log_type=LogLevel.LOG_SUCCESS, no_date=True)
        else:
            LOGGER.log("Skipped", log_type=LogLevel.LOG_SUCCESS, no_date=True)

        LOGGER.log("Installing AWS cli...", end="")
        if not simulate:
            if sys.platform.startswith('linux'):
                ok = os.system('curl "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o "' + CFG.settings[
                    'basepath'] + '/awscliv2.zip" --silent')
                if ok > 0:
                    LOGGER.log("Dependencies installation failed", log_type=LogLevel.LOG_ERROR, no_date=True)
                    return 212
                ok = os.system('unzip -oq ' + CFG.settings['basepath'] + '/awscliv2.zip -d ' + CFG.settings['basepath'])
                if ok > 0:
                    LOGGER.log("Dependencies installation failed", log_type=LogLevel.LOG_ERROR, no_date=True)
                    return 213
                ok = os.system('rm ' + CFG.settings['basepath'] + '/awscliv2.zip')
                if ok > 0:
                    LOGGER.log("Dependencies installation failed", log_type=LogLevel.LOG_ERROR, no_date=True)
                    return 214
                ok = os.system('sudo ' + CFG.settings['basepath'] + '/aws/install --update')
                if ok > 0:
                    LOGGER.log("Dependencies installation failed", log_type=LogLevel.LOG_ERROR, no_date=True)
                    return 215
                LOGGER.log("OK", log_type=LogLevel.LOG_SUCCESS, no_date=True)
            else:
                LOGGER.log("OS is not Linux", log_type=LogLevel.LOG_SUCCESS, no_date=True)
        else:
            LOGGER.log("Skipped", log_type=LogLevel.LOG_SUCCESS, no_date=True)

        LOGGER.log("Installing python dependencies...", end="")
        if not simulate:
            if sys.platform.startswith('linux'):
                ok = os.system(f"sudo pip3 install -r {CFG.settings['basepath']}/requirements.txt > /dev/null")
                if ok > 0:
                    LOGGER.log("Dependencies installation failed", log_type=LogLevel.LOG_ERROR, no_date=True)
                    return 216
                LOGGER.log("OK", log_type=LogLevel.LOG_SUCCESS, no_date=True)
            elif sys.platform.startswith('win32'):
                cmd = f"python3 -m pip install -r {CFG.settings['basepath']}\\requirements.txt 1> nul"
                ok = os.system(cmd)
                if ok > 0:
                    LOGGER.log("Dependencies installation failed", log_type=LogLevel.LOG_ERROR, no_date=True)
                    return 216
                LOGGER.log("OK", log_type=LogLevel.LOG_SUCCESS, no_date=True)
            else:
                LOGGER.log("OS is neither Windows or Linux", log_type=LogLevel.LOG_ERROR, no_date=True)
        else:
            LOGGER.log("Skipped", log_type=LogLevel.LOG_SUCCESS, no_date=True)

        LOGGER.log("Configuring AWS credentials...", end="")
        if not simulate:
            if not os.path.exists(CFG.settings['homepath'] + '/.aws'):
                os.mkdir(CFG.settings['homepath'] + '/.aws')

            write_in_file(CFG.settings['homepath'] + '/.aws/config',
                          '[default]\r\nregion=' + CFG.settings['aws'][
                              'region'] + '\r\noutput=json\r\naws_access_key_id=' +
                          CFG.settings['aws']['accesskey'] + '\r\naws_secret_access_key=' + CFG.settings['aws'][
                              'secretkey'])

            LOGGER.log("OK", log_type=LogLevel.LOG_SUCCESS, no_date=True)
        else:
            LOGGER.log("Skipped", log_type=LogLevel.LOG_SUCCESS, no_date=True)

        LOGGER.log("Testing AWS S3 connection...", end="")
        AWS_S3: PolyAWSS3 = PolyAWSS3(aws_region=CFG.settings['aws']['region'],
                                      aws_bucket=CFG.settings['aws']['bucket'])
        ok = os.system('echo "Success" > ' + CFG.settings['basepath'] + '/test_successful.txt')
        if ok != 0:
            LOGGER.log("Creating temp file for connection test to S3", log_type=LogLevel.LOG_ERROR, no_date=True)
            return 300
        ok = AWS_S3.s3_upload_file(CFG.settings['basepath'] + '/test_successful.txt',
                                   'Unity/steam-parameters/test_successful.txt')
        if ok != 0:
            LOGGER.log("Error uploading file to S3 Unity/steam-parameters. Check the IAM permissions",
                       log_type=LogLevel.LOG_ERROR,
                       no_date=True)
            return 301
        ok = AWS_S3.s3_delete_file('Unity/steam-parameters/test_successful.txt')
        if ok != 0:
            LOGGER.log("Error deleting file from S3 Unity/steam-parameters. Check the IAM permissions",
                       log_type=LogLevel.LOG_ERROR,
                       no_date=True)
            return 302
        ok = AWS_S3.s3_upload_file(CFG.settings['basepath'] + '/test_successful.txt',
                                   'Unity/unity-builds/test_successful.txt')
        if ok != 0:
            LOGGER.log("Error uploading file to S3 Unity/unity-builds. Check the IAM permissions",
                       log_type=LogLevel.LOG_ERROR,
                       no_date=True)
            return 303
        ok = AWS_S3.s3_delete_file('Unity/unity-builds/test_successful.txt')
        if ok != 0:
            LOGGER.log("Error deleting file from S3 Unity/unity-builds. Check the IAM permissions",
                       log_type=LogLevel.LOG_ERROR,
                       no_date=True)
            return 302
        os.remove(CFG.settings['basepath'] + '/test_successful.txt')
        ok = os.path.exists(CFG.settings['basepath'] + '/test_successful.txt')
        if ok != 0:
            LOGGER.log("Error deleting after connecting to S3", log_type=LogLevel.LOG_ERROR, no_date=True)
            return 304
        LOGGER.log("OK", log_type=LogLevel.LOG_SUCCESS, no_date=True)

        LOGGER.log("Testing AWS DynamoDB connection...", end="")
        AWS_DDB: PolyAWSDynamoDB = PolyAWSDynamoDB(aws_region=CFG.settings['aws']['region'],
                                                   dynamodb_table=CFG.settings['aws']['dynamodbtable'])
        packages: Dict[str, Package] = AWS_DDB.get_packages_data()
        if len(packages.keys()) > 0:
            ok = 0

        if ok != 0:
            LOGGER.log("Error connection to AWS DynamoDB", log_type=LogLevel.LOG_ERROR, no_date=True)
            return 304
        LOGGER.log("OK", log_type=LogLevel.LOG_SUCCESS, no_date=True)

        LOGGER.log("Installing Unity-steam startup script...", end="")
        if not simulate:
            if sys.platform.startswith('linux'):
                shutil.copyfile(CFG.settings['basepath'] + '/Unity-steam-startup-script.example',
                                CFG.settings['basepath'] + '/Unity-steam-startup-script')
                replace_in_file(CFG.settings['basepath'] + '/Unity-steam-startup-script', '%basepath%',
                                CFG.settings['basepath'])
                ok = os.system(
                    'sudo mv ' + CFG.settings[
                        'basepath'] + '/Unity-steam-startup-script /etc/init.d/Unity-steam-startup-script > /dev/null')
                if ok != 0:
                    LOGGER.log("Error copying Unity-steam startup script file to /etc/init.d",
                               log_type=LogLevel.LOG_ERROR, no_date=True)
                    return 310
                ok = os.system(
                    'sudo chown root:root /etc/init.d/Unity-steam-startup-script ; sudo chmod 755 /etc/init.d/Unity-steam-startup-script ; sudo systemctl daemon-reload > /dev/null')
                if ok > 0:
                    LOGGER.log("Error setting permission to Unity-steam startup script file",
                               log_type=LogLevel.LOG_ERROR,
                               no_date=True)
                    return 311
                LOGGER.log("OK", log_type=LogLevel.LOG_SUCCESS, no_date=True)
            else:
                LOGGER.log("OS is not Linux", log_type=LogLevel.LOG_SUCCESS, no_date=True)
        else:
            LOGGER.log("Skipped", log_type=LogLevel.LOG_SUCCESS, no_date=True)

        for store in PLUGIN_MANAGER.store_plugins.values():
            store.install(simulate)
        for hook in PLUGIN_MANAGER.hook_plugins.values():
            hook.install(simulate)

        LOGGER.log("Testing Unity connection...", end="")
        UCB_builds_test = UCB.get_last_builds(platform=platform)
        if UCB_builds_test is None:
            LOGGER.log("Error connecting to Unity", log_type=LogLevel.LOG_ERROR, no_date=True)
            return 21
        LOGGER.log("OK", log_type=LogLevel.LOG_SUCCESS, no_date=True)

        for store in PLUGIN_MANAGER.store_plugins.values():
            store.test()
        for hook in PLUGIN_MANAGER.hook_plugins.values():
            hook.test()

        LOGGER.log("Testing email notification...", end="")
        if not no_email:
            str_log = '<b>Result of the Unity-steam script installation:</b>\r\n</br>\r\n</br>'
            str_log = str_log + read_from_file(LOGGER.log_file_path)
            str_log = str_log + '\r\n</br>\r\n</br><font color="GREEN">Everything is set up correctly. Congratulations !</font>'
            AWS_SES_client: PolyAWSSES = PolyAWSSES(CFG.settings['aws']['region'])
            ok = AWS_SES_client.send_email(sender=CFG.settings['email']['from'],
                                           recipients=CFG.settings['email']['recipients'],
                                           title="Steam build notification test",
                                           message=str_log, quiet=True)
            if ok != 0:
                LOGGER.log("Error sending email", log_type=LogLevel.LOG_ERROR, no_date=True)
                return 35
            LOGGER.log("OK", log_type=LogLevel.LOG_SUCCESS, no_date=True)
        else:
            LOGGER.log("Not tested (--noemail flag used)", log_type=LogLevel.LOG_WARNING, no_date=True)

        LOGGER.log("Everything is set up correctly. Congratulations !", log_type=LogLevel.LOG_SUCCESS)

        return 0
    # endregion

    # region PACKAGES CONFIG
    LOGGER.log(f"Retrieving configuration from DynamoDB (table {CFG.settings['aws']['dynamodbtable']})...", end="")
    PACKAGE_MANAGER.load_config(environments=environments)
    LOGGER.log("OK", no_date=True, log_type=LogLevel.LOG_SUCCESS)
    # endregion

    # region SHOW CONFIG
    if show_config:
        LOGGER.log(f"Displaying configuration...")
        LOGGER.log('', no_date=True)

        print_config(packages=PACKAGE_MANAGER.packages)

        return 0
    # endregion

    # region Unity builds information query
    # Get all the successful builds from Unity Cloud Build
    build_filter = ""
    if platform != "":
        build_filter = f"(Filtering on platform:{platform})"
    if build_filter != "":
        LOGGER.log(f"Retrieving all the builds information from Unity {build_filter}...", end="")
    else:
        LOGGER.log(f"Retrieving all the builds information from Unity...", end="")

    UCB_all_builds: List[Build] = UCB.get_builds(platform=platform)
    if len(UCB_all_builds) == 0:
        if force:
            LOGGER.log("No build available in Unity but process forced to continue (--force flag used)",
                       log_type=LogLevel.LOG_WARNING,
                       no_date=True)
        elif show_diag:
            LOGGER.log("No build available in Unity but process forced to continue (--showdiag flag used)",
                       log_type=LogLevel.LOG_WARNING,
                       no_date=True)
        else:
            LOGGER.log("No build available in Unity", log_type=LogLevel.LOG_SUCCESS, no_date=True)
            return 3
    else:
        LOGGER.log("OK", log_type=LogLevel.LOG_SUCCESS, no_date=True)

    # filter on successful builds only
    LOGGER.log(f" {len(UCB.builds_categorized['success'])} builds are successful and waiting for processing",
               log_type=LogLevel.LOG_SUCCESS)
    if len(UCB.builds_categorized['building']) > 0:
        LOGGER.log(f" {len(UCB.builds_categorized['building'])} builds are building", log_type=LogLevel.LOG_WARNING,
                   no_prefix=True)
    if len(UCB.builds_categorized['failure']) > 0:
        LOGGER.log(f" {len(UCB.builds_categorized['failure'])} builds are failed", log_type=LogLevel.LOG_ERROR,
                   no_prefix=True)
    if len(UCB.builds_categorized['canceled']) > 0:
        LOGGER.log(f" {len(UCB.builds_categorized['canceled'])} builds are canceled", log_type=LogLevel.LOG_ERROR,
                   no_prefix=True)
    if len(UCB.builds_categorized['unknown']) > 0:
        LOGGER.log(f" {len(UCB.builds_categorized['unknown'])} builds are in a unknown state",
                   log_type=LogLevel.LOG_WARNING,
                   no_prefix=True)
    # endregion

    # region PACKAGE COMPLETION CHECK
    LOGGER.log(f"Compiling Unity data with configuration...", end="")

    # identify the full completion of a package (based on the configuration)
    for package in PACKAGE_MANAGER.packages.values():
        package.update_completion(UCB_all_builds)

    LOGGER.log("OK", no_date=True, log_type=LogLevel.LOG_SUCCESS)
    # endregion

    # region SHOW DIAG
    if show_diag:
        LOGGER.log(f"Displaying diagnostics...")
        LOGGER.log('', no_date=True)

        print_config(packages=PACKAGE_MANAGER.packages, with_diag=True)

        return 0
    # endregion

    can_continue = False
    for package_name, package in PACKAGE_MANAGER.packages.items():
        if package.complete:
            can_continue = True

    LOGGER.log(" One or more packages complete...", end="")
    if can_continue:
        LOGGER.log("OK", no_date=True, log_type=LogLevel.LOG_SUCCESS)
    elif force:
        LOGGER.log(f"Process forced to continue (--force flag used)", no_date=True, log_type=LogLevel.LOG_WARNING)
    else:
        LOGGER.log("At least one package must be complete to proceed to the next step", no_date=True,
                   log_type=LogLevel.LOG_ERROR)
        return 4

    # region DOWNLOAD
    if not no_download:
        LOGGER.log("--------------------------------------------------------------------------", no_date=True)
        LOGGER.log("Downloading build from Unity...")
        PACKAGE_MANAGER.download_builds(force=force, simulate=simulate, no_s3upload=no_s3upload)

    # endregion

    # region VERSION
    LOGGER.log("--------------------------------------------------------------------------", no_date=True)
    LOGGER.log("Getting version...")
    version_found: bool = False
    already_versioned_build_targets: List[str] = list()
    for package_name, package in PACKAGE_MANAGER.packages.items():
        if package.complete:
            build_targets = package.get_build_targets()
            for build_target in build_targets:
                if not already_versioned_build_targets.__contains__(build_target.name):
                    # let's make sure that we'll not extract the version twice
                    already_versioned_build_targets.append(build_target.name)

                    build_os_path = f"{CFG.settings['buildpath']}/{build_target.name}"

                    if not version_found:
                        if steam_appversion == "":
                            LOGGER.log(' Getting the version of the build from files...', end="")
                            pathFileVersion = glob.glob(build_os_path + "/**/UCB_version.txt", recursive=True)

                            if len(pathFileVersion) == 1:
                                if os.path.exists(pathFileVersion[0]):
                                    steam_appversion = read_from_file(pathFileVersion[0])
                                    steam_appversion = steam_appversion.rstrip('\n')
                                    # if not simulate:
                                    #    os.remove(pathFileVersion[0])

                                if steam_appversion != "":
                                    version_found = True
                                    LOGGER.log(" " + steam_appversion + " ", log_type=LogLevel.LOG_INFO, no_date=True,
                                               end="")
                                    LOGGER.log("OK ", log_type=LogLevel.LOG_SUCCESS, no_date=True)
                            else:
                                LOGGER.log(
                                    f"File version UCB_version.txt was not found in build directory {build_os_path}",
                                    log_type=LogLevel.LOG_WARNING, no_date=True)
                        else:
                            version_found = True
                            LOGGER.log(' Getting the version of the build from argument...', end="")
                            LOGGER.log(" " + steam_appversion + " ", log_type=LogLevel.LOG_INFO, no_date=True, end="")
                            LOGGER.log("OK ", log_type=LogLevel.LOG_SUCCESS, no_date=True)
    # endregion

    # region UPLOAD
    if not no_upload:
        LOGGER.log("--------------------------------------------------------------------------", no_date=True)
        LOGGER.log("Uploading files to stores...")

        for package_name, package in PACKAGE_MANAGER.packages.items():
            package.uploaded = False

        # region STEAM
        for package_name, package in PACKAGE_MANAGER.packages.items():
            first: bool = True

            # we only want to build the packages that are complete and filter on wanted one (see arguments)
            if StoreType.STEAM in package.stores and (len(stores) == 0 or stores.__contains__("steam")):
                if package.complete:
                    LOGGER.log(f'Starting Steam process for package {package_name}...')
                    app_id = ""
                    build_path = ""

                    for build_target_id, build_target in package.stores[StoreType.STEAM].items():
                        # find the data related to the branch we want to build
                        depot_id = build_target.parameters['depot_id']
                        branch_name = build_target.parameters['branch_name']
                        live = build_target.parameters['live']
                        build_path = f"{CFG.settings['buildpath']}/{build_target_id}"

                        # now prepare the steam files
                        # first time we loop: prepare the main steam file
                        if first:
                            first = False

                            app_id = build_target.parameters['app_id']
                            LOGGER.log(f' Preparing main Steam file for app {app_id}...', end="")
                            if not simulate:
                                shutil.copyfile(f"{steam_scripts_path}/template_app_build.vdf",
                                                f"{steam_scripts_path}/app_build_{app_id}.vdf")

                                replace_in_file(f"{steam_scripts_path}/app_build_{app_id}.vdf",
                                                "%basepath%", CFG.settings['basepath'])
                                replace_in_file(f"{steam_scripts_path}/app_build_{app_id}.vdf",
                                                "%version%", steam_appversion)
                                replace_in_file(f"{steam_scripts_path}/app_build_{app_id}.vdf",
                                                "%branch_name%", branch_name)
                                replace_in_file(f"{steam_scripts_path}/app_build_{app_id}.vdf",
                                                "%app_id%", app_id)

                                if no_live or not live:
                                    replace_in_file(f"{steam_scripts_path}/app_build_{app_id}.vdf",
                                                    "%live%", "")
                                else:
                                    replace_in_file(f"{steam_scripts_path}/app_build_{app_id}.vdf",
                                                    "%live%", branch_name)

                            LOGGER.log("OK", log_type=LogLevel.LOG_SUCCESS, no_date=True)

                        # then the depot files
                        LOGGER.log(f' Preparing platform Steam file for depot {depot_id} / {build_target_id}...',
                                   end="")
                        if not simulate:
                            shutil.copyfile(
                                f"{steam_scripts_path}/template_depot_build_buildtarget.vdf",
                                f"{steam_scripts_path}/depot_build_{build_target_id}.vdf")

                            replace_in_file(
                                f"{steam_scripts_path}/depot_build_{build_target_id}.vdf",
                                "%depot_id%", depot_id)
                            replace_in_file(
                                f"{steam_scripts_path}/depot_build_{build_target_id}.vdf",
                                "%buildtargetid%", build_target_id)
                            replace_in_file(
                                f"{steam_scripts_path}/depot_build_{build_target_id}.vdf",
                                "%basepath%", CFG.settings['basepath'])

                            data = vdf.load(open(f"{steam_scripts_path}/app_build_{app_id}.vdf"))
                            data['appbuild']['depots'][depot_id] = f"depot_build_{build_target_id}.vdf"

                            indented_vdf = vdf.dumps(data, pretty=True)

                            write_in_file(f"{steam_scripts_path}/app_build_{app_id}.vdf",
                                          indented_vdf)

                        LOGGER.log("OK", log_type=LogLevel.LOG_SUCCESS, no_date=True)

                    LOGGER.log(f" Cleaning non necessary files...", end="")
                    if not simulate and build_path != "":
                        filepath: str = f"{build_path}/bitbucket-pipelines.yml"
                        if os.path.exists(filepath):
                            LOGGER.log(f"{filepath}...", end="")
                            LOGGER.log("OK", log_type=LogLevel.LOG_SUCCESS, no_date=True)
                            os.remove(filepath)

                        filepath = f"{build_path}/appspec.yml"
                        if os.path.exists(filepath):
                            LOGGER.log(f"{filepath}...", end="")
                            LOGGER.log("OK", log_type=LogLevel.LOG_SUCCESS, no_date=True)
                            os.remove(filepath)

                        filepath = f"{build_path}/buildspec.yml"
                        if os.path.exists(filepath):
                            LOGGER.log(f"{filepath}...", end="")
                            LOGGER.log("OK", log_type=LogLevel.LOG_SUCCESS, no_date=True)
                            os.remove(filepath)
                    LOGGER.log("OK", log_type=LogLevel.LOG_SUCCESS, no_date=True)

                    LOGGER.log(" Building Steam packages...", end="")
                    if app_id != "":
                        cmd = f'''{steam_exe_path} +login "{CFG.settings['steam']['user']}" "{CFG.settings['steam']['password']}" +run_app_build {steam_scripts_path}/app_build_{app_id}.vdf +quit'''
                        if not simulate:
                            ok = os.system(cmd)
                        else:
                            ok = 0

                        if ok != 0:
                            LOGGER.log(f" Executing the bash file {steam_exe_path} (exitcode={ok})",
                                       log_type=LogLevel.LOG_ERROR, no_date=True)
                            return 9

                        package.uploaded = True

                        LOGGER.log("OK", log_type=LogLevel.LOG_SUCCESS, no_date=True)

                        if simulate:
                            LOGGER.log("  " + cmd)
                    else:
                        LOGGER.log("app_id is empty", log_type=LogLevel.LOG_ERROR, no_date=True)
                        return 9
                else:
                    if package.concerned:
                        LOGGER.log(f' Package {package_name} is not complete and will not be processed for Steam...',
                                   log_type=LogLevel.LOG_WARNING)
        # endregion

        # region BUTLER
        for package_name, package in PACKAGE_MANAGER.packages.items():
            # we only want to build the packages that are complete
            if StoreType.ITCH in package.stores and (len(stores) == 0 or stores.__contains__("itch")):
                if package.complete:
                    LOGGER.log(f'Starting Butler process for package {package_name}...')

                    for build_target_id, build_target in package.stores[StoreType.ITCH].items():
                        # find the data related to the branch we want to build
                        butler_channel = build_target.parameters['channel']
                        build_path = f"{steam_build_path}/{build_target_id}"

                        ok: int = upload_to_butler(build_target_id=build_target_id, build_path=build_path,
                                                   butler_channel=butler_channel, app_version=steam_appversion,
                                                   simulate=simulate)

                        if ok == 0:
                            package.uploaded = True
                        elif ok == 256:
                            LOGGER.log(" BUTLER upload failed, 2nd try...", log_type=LogLevel.LOG_WARNING)
                            ok = upload_to_butler(build_target_id=build_target_id, build_path=build_path,
                                                  butler_channel=butler_channel, app_version=steam_appversion,
                                                  simulate=simulate)
                            if ok == 0:
                                package.uploaded = True
                            else:
                                return 12

                else:
                    if package.concerned:
                        LOGGER.log(f' Package {package_name} is not complete and will not be processed for Butler...',
                                   log_type=LogLevel.LOG_WARNING)
        # endregion
    # endregion

    # region CLEAN
    if not no_clean:
        LOGGER.log("--------------------------------------------------------------------------", no_date=True)
        LOGGER.log("Cleaning successfully upload build in Unity...")

        already_cleaned_build_targets: List[str] = list()
        # let's remove the build successfully uploaded to Steam or Butler from Unity
        # clean only the packages that are successful
        for package_name, package in PACKAGE_MANAGER.packages.items():
            if package.complete and package.uploaded:
                LOGGER.log(f" Cleaning package {package_name}...")
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

                package.cleaned = cleaned

        # additional cleaning steps
        LOGGER.log(f"  Deleting additional files...", end="")

        LOGGER.log("OK", log_type=LogLevel.LOG_SUCCESS, no_date=True)

    # endregion

    # region NOTIFY
    LOGGER.log("--------------------------------------------------------------------------", no_date=True)
    LOGGER.log("Notify successfully building process to BitBucket...")
    BITBUCKET: PolyBitBucket = PolyBitBucket(bitbucket_username=CFG.settings['bitbucket']['username'],
                                             bitbucket_app_password=CFG.settings['bitbucket']['app_password'],
                                             bitbucket_cloud=True,
                                             bitbucket_workspace=CFG.settings['bitbucket']['workspace'],
                                             bitbucket_repository=CFG.settings['bitbucket']['repository'])

    already_notified_build_targets: List[str] = list()
    # let's notify BitBucket that everything is done
    for package_name, package in PACKAGE_MANAGER.packages.items():
        if HookType.BITBUCKET in package.hooks and (len(hooks) == 0 or hooks.__contains__("bitbucket")):
            if package.complete and package.uploaded and package.cleaned:
                if not already_notified_build_targets.__contains__(package_name):
                    LOGGER.log(f" Notifying package {package_name}...", end="")
                    if not simulate:
                        package.notified = BITBUCKET.trigger_pipeline(
                            package.hooks[HookType.BITBUCKET].parameters['branch'],
                            package.hooks[HookType.BITBUCKET].parameters['pipeline'])
                        package.hooks[HookType.BITBUCKET].notified = True
                    LOGGER.log("OK", log_type=LogLevel.LOG_SUCCESS, no_date=True)

                    # let's make sure that we'll not notify twice
                    already_notified_build_targets.append(package_name)

    # end region

    LOGGER.log("--------------------------------------------------------------------------", no_date=True)
    LOGGER.log("All done!", log_type=LogLevel.LOG_SUCCESS)
    return 0


if __name__ == "__main__":
    code_ok = 0
    no_shutdown = False
    no_email = False
    try:
        options, arguments = getopt.getopt(sys.argv[1:], "hldocsfip:lv:t:u:a:",
                                           ["help", "nolive", "nodownload", "nos3upload", "noupload", "noclean",
                                            "noshutdown",
                                            "noemail",
                                            "force", "install", "simulate", "showconfig", "showdiag", "platform=",
                                            "store=",
                                            "environment=",
                                            "version=",
                                            "steamuser=",
                                            "steampassword="])
        for option, argument in options:
            if option in ("-s", "--noshutdown"):
                no_shutdown = True
            elif option in ("-i", "--noemail"):
                no_email = True
            elif option in ("-i", "--install"):
                no_shutdown = True
    except getopt.GetoptError:
        LOGGER.log(log_type=LogLevel.LOG_ERROR, message=f'parameter error: {getopt.GetoptError.msg}')
        print_help()
        code_ok = 11

    if code_ok != 10 and code_ok != 11:
        code_ok = main(sys.argv[1:])
        if not no_shutdown and code_ok != 10:
            LOGGER.log("Shutting down computer...")
            os.system("sudo shutdown +3")

    execution_time: float = round((time.time() - start_time), 4)
    LOGGER.log(f"--- Script execution time : {execution_time} seconds ---")
    # close the logfile
    LOGGER.close()
    if code_ok != 10 and code_ok != 11 and not no_email:
        AWS_SES: PolyAWSSES = PolyAWSSES(CFG.settings['aws']['region'])
        AWS_SES.send_email(sender=CFG.settings['email']['from'], recipients=CFG.settings['email']['recipients'],
                           title="Steam build result",
                           message=read_from_file(LOGGER.name))
