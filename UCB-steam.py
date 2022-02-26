__version__ = "0.31"

import array
import getopt
import glob
import os
import shutil
import sys
import time
from typing import Dict, List

from librairies import LOGGER, CFG, PACKAGE_MANAGER, PLUGIN_MANAGER
from librairies.AWS import AWS_DDB, AWS_S3
from librairies.AWS.aws import PolyAWSSES
from librairies.Unity import UCB
from librairies.Unity.classes import Build
from librairies.common import errors
from librairies.common.libraries import write_in_file, replace_in_file, read_from_file
from librairies.common.package import Package
from librairies.logger import LogLevel

start_time = time.time()


# region HELPER LIBRARY
def print_help():
    print(
        f"Unity-steam.py [--platform=(standalonelinux64, standaloneosxuniversal, standalonewindows64)] [--environment=(environment1, environment2, ...)] [--store=(store1,store2,...)] [--nolive] [--force] [--version=<version>] [--install] [--nodownload] [--nos3upload] [--noupload] [--noclean] [--noshutdown] [--noemail] [--simulate] [--showconfig | --showdiag] [--steamuser=<steamuser>] [--steampassword=<steampassword>]")


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
        return errors.INVALID_PARAMETERS

    for option, argument in options:
        if option in ("-h", "--help"):
            print_help()
            return errors.INVALID_PARAMETERS
        elif option in ("-p", "--platform"):
            if argument != "standalonelinux64" and argument != "standaloneosxuniversal" and argument != "standalonewindows64":
                LOGGER.log(log_type=LogLevel.LOG_ERROR,
                           message="parameter --platform takes only standalonelinux64, standaloneosxuniversal or standalonewindows64 as valid value")
                print_help()
                return errors.INVALID_PARAMETERS
            platform = argument
        elif option == "--store":
            stores = argument.split(',')
            if len(stores) == 0:
                LOGGER.log(log_type=LogLevel.LOG_ERROR, message="parameter --store must have at least one value")
                print_help()
                return errors.INVALID_PARAMETERS
        elif option == "--environment":
            environments = argument.split(',')
            if len(environments) == 0:
                LOGGER.log(log_type=LogLevel.LOG_ERROR, message="parameter --environment must have at least one value")
                print_help()
                return errors.INVALID_PARAMETERS
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
                    return errors.APT_UPDATE_FAILED
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
                    return errors.APT_INSTALL_FAILED
                LOGGER.log("OK", log_type=LogLevel.LOG_SUCCESS, no_date=True)
            elif sys.platform.startswith('win32'):
                ok = os.system("python.exe -m pip install --upgrade pip --no-warn-script-location 1> nul")
                if ok > 0:
                    LOGGER.log("Dependencies installation failed", log_type=LogLevel.LOG_ERROR, no_date=True)
                    return errors.PYTHON_INSTALLATION_FAILED
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
                    return errors.AWS_DOWNLOAD_DEPENDENCIES_FAILED
                ok = os.system('unzip -oq ' + CFG.settings['basepath'] + '/awscliv2.zip -d ' + CFG.settings['basepath'])
                if ok > 0:
                    LOGGER.log("Dependencies installation failed", log_type=LogLevel.LOG_ERROR, no_date=True)
                    return errors.AWS_UNZIP_DEPENDENCIES_FAILED
                ok = os.system('rm ' + CFG.settings['basepath'] + '/awscliv2.zip')
                if ok > 0:
                    LOGGER.log("Dependencies installation failed", log_type=LogLevel.LOG_ERROR, no_date=True)
                    return errors.AWS_CLEAN_DEPENDENCIES_FAILED
                ok = os.system('sudo ' + CFG.settings['basepath'] + '/aws/install --update')
                if ok > 0:
                    LOGGER.log("Dependencies installation failed", log_type=LogLevel.LOG_ERROR, no_date=True)
                    return errors.AWS_INSTALL_DEPENDENCIES_FAILED
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
                    return errors.PYTHON_INSTALL_DEPENDENCIES_FAILED
                LOGGER.log("OK", log_type=LogLevel.LOG_SUCCESS, no_date=True)
            elif sys.platform.startswith('win32'):
                cmd = f"python3 -m pip install -r {CFG.settings['basepath']}\\requirements.txt 1> nul"
                ok = os.system(cmd)
                if ok > 0:
                    LOGGER.log("Dependencies installation failed", log_type=LogLevel.LOG_ERROR, no_date=True)
                    return errors.PYTHON_INSTALL_DEPENDENCIES_FAILED
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
        ok = os.system('echo "Success" > ' + CFG.settings['basepath'] + '/test_successful.txt')
        if ok != 0:
            LOGGER.log("Creating temp file for connection test to S3", log_type=LogLevel.LOG_ERROR, no_date=True)
            return errors.AWS_S3_TEMP_FILE_CREATION_TEST_FAILED
        ok = AWS_S3.s3_upload_file(CFG.settings['basepath'] + '/test_successful.txt',
                                   'Unity/steam-parameters/test_successful.txt')
        if ok != 0:
            LOGGER.log("Error uploading file to S3 Unity/steam-parameters. Check the IAM permissions",
                       log_type=LogLevel.LOG_ERROR,
                       no_date=True)
            return errors.AWS_S3_UPLOAD1_TEST_FAILED
        ok = AWS_S3.s3_delete_file('Unity/steam-parameters/test_successful.txt')
        if ok != 0:
            LOGGER.log("Error deleting file from S3 Unity/steam-parameters. Check the IAM permissions",
                       log_type=LogLevel.LOG_ERROR,
                       no_date=True)
            return errors.AWS_S3_DELETE1_TEST_FAILED
        ok = AWS_S3.s3_upload_file(CFG.settings['basepath'] + '/test_successful.txt',
                                   'Unity/unity-builds/test_successful.txt')
        if ok != 0:
            LOGGER.log("Error uploading file to S3 Unity/unity-builds. Check the IAM permissions",
                       log_type=LogLevel.LOG_ERROR,
                       no_date=True)
            return errors.AWS_S3_UPLOAD2_TEST_FAILED
        ok = AWS_S3.s3_delete_file('Unity/unity-builds/test_successful.txt')
        if ok != 0:
            LOGGER.log("Error deleting file from S3 Unity/unity-builds. Check the IAM permissions",
                       log_type=LogLevel.LOG_ERROR,
                       no_date=True)
            return errors.AWS_S3_DELETE2_TEST_FAILED
        os.remove(CFG.settings['basepath'] + '/test_successful.txt')
        ok = os.path.exists(CFG.settings['basepath'] + '/test_successful.txt')
        if ok != 0:
            LOGGER.log("Error deleting after connecting to S3", log_type=LogLevel.LOG_ERROR, no_date=True)
            return errors.AWS_S3_CLEAN_TEST_FAILED
        LOGGER.log("OK", log_type=LogLevel.LOG_SUCCESS, no_date=True)

        LOGGER.log("Testing AWS DynamoDB connection...", end="")
        packages: Dict[str, Package] = AWS_DDB.get_packages_data()
        if len(packages.keys()) > 0:
            ok = 0

        if ok != 0:
            LOGGER.log("Error connection to AWS DynamoDB", log_type=LogLevel.LOG_ERROR, no_date=True)
            return errors.AWS_DDB_CONNECTION_TEST_FAILED
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
                    return errors.UNITY_STARTUP_SCRIPT_INSTALLATION_FAILED
                ok = os.system(
                    'sudo chown root:root /etc/init.d/Unity-steam-startup-script ; sudo chmod 755 /etc/init.d/Unity-steam-startup-script ; sudo systemctl daemon-reload > /dev/null')
                if ok > 0:
                    LOGGER.log("Error setting permission to Unity-steam startup script file",
                               log_type=LogLevel.LOG_ERROR,
                               no_date=True)
                    return errors.UNITY_CHOWN_INSTALLATION_FAILED
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
            return errors.UNITY_CONNECTION_TEST_FAILED
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
                return errors.EMAIL_CONNECTION_TEST_FAILED
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

        PACKAGE_MANAGER.print_config(with_diag=False)

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
            return errors.UCB_NO_BUILD_AVAILABLE
    else:
        LOGGER.log("OK", log_type=LogLevel.LOG_SUCCESS, no_date=True)

    # filter on successful builds only
    UCB.display_builds_details()
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

        PACKAGE_MANAGER.print_config(with_diag=True)

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
        return errors.NO_PACKAGE_COMPLETE

    # region DOWNLOAD
    if not no_download:
        LOGGER.log("--------------------------------------------------------------------------", no_date=True)
        LOGGER.log("Downloading build from Unity...")
        ok: int = PACKAGE_MANAGER.download_builds(force=force, simulate=simulate, no_s3upload=no_s3upload)

        if ok != 0:
            return ok

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

    if not version_found:
        LOGGER.log("No version file found", log_type=LogLevel.LOG_ERROR)
        return errors.VERSION_FILE_NOT_FOUND
    # endregion

    # region UPLOAD
    if not no_upload:
        LOGGER.log("--------------------------------------------------------------------------", no_date=True)
        LOGGER.log("Uploading files to stores...")

        ok: int = PACKAGE_MANAGER.upload_builds(simulate=simulate, app_version=steam_appversion, stores=stores)

        if ok != 0:
            return ok
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
