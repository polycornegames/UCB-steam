__version__ = "0.31"

import array
import getopt
import os
import shutil
import sys
import time
from typing import List

import requests
import urllib3

from librairies import LOGGER, CFG, PACKAGE_MANAGER, PLUGIN_MANAGER
from librairies.AWS import AWS_DDB, AWS_S3
from librairies.AWS.aws import PolyAWSSES
from librairies.Unity import UCB
from librairies.Unity.classes import Build
from librairies.common import errors
from librairies.common.libraries import write_in_file, replace_in_file, read_from_file, print_help
from librairies.logger import LogLevel

start_time = time.time()


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
    no_notify = False

    force_all = False
    force_download = False
    force_upload = False
    force_clean = False
    force_notify = False

    install = False
    show_config = False
    show_diag = False
    no_live = False
    simulate = False

    exitcode: int = 0

    # region ARGUMENTS CHECK
    try:
        options, arguments = getopt.getopt(argv, "h",
                                           ["help", "nolive", "nodownload", "nos3upload", "noupload", "noclean",
                                            "nonotify",
                                            "noshutdown",
                                            "noemail",
                                            "forceall",
                                            "forcedownload",
                                            "forceupload",
                                            "forceclean",
                                            "forcenotify",
                                            "install", "simulate", "showconfig", "showdiag", "platform=",
                                            "store=",
                                            "hook=",
                                            "environment=",
                                            "version=",
                                            "steamuser=",
                                            "steampassword="])
    except getopt.GetoptError:
        LOGGER.log(log_type=LogLevel.LOG_ERROR, message=f'parameter error: {getopt.GetoptError.msg}')
        print()
        exitcode = errors.INVALID_PARAMETERS1

    for option, argument in options:
        if option in ("-h", "--help"):
            print_help()
            exitcode = errors.INVALID_PARAMETERS1
        elif option == "--platform":
            if argument != "standalonelinux64" and argument != "standaloneosxuniversal" and argument != "standalonewindows64":
                LOGGER.log(log_type=LogLevel.LOG_ERROR,
                           message="parameter --platform takes only standalonelinux64, standaloneosxuniversal or standalonewindows64 as valid value")
                print_help()
                exitcode = errors.INVALID_PARAMETERS1
            platform = argument
        elif option == "--store":
            stores = argument.split(',')
            if len(stores) == 0:
                LOGGER.log(log_type=LogLevel.LOG_ERROR, message="parameter --store must have at least one value")
                print_help()
                exitcode = errors.INVALID_PARAMETERS1
        elif option == "--hook":
            hooks = argument.split(',')
            if len(hooks) == 0:
                LOGGER.log(log_type=LogLevel.LOG_ERROR, message="parameter --hook must have at least one value")
                print_help()
                exitcode = errors.INVALID_PARAMETERS1
        elif option == "--environment":
            environments = argument.split(',')
            if len(environments) == 0:
                LOGGER.log(log_type=LogLevel.LOG_ERROR, message="parameter --environment must have at least one value")
                print_help()
                exitcode = errors.INVALID_PARAMETERS1
        elif option == "--install":
            no_download = True
            no_upload = True
            no_clean = True
            install = True
        elif option == "--nodownload":
            no_download = True
        elif option == "--nos3upload":
            no_s3upload = True
        elif option == "--noupload":
            no_upload = True
        elif option == "--noclean":
            no_clean = True
        elif option == "--nonotify":
            no_notify = True
        elif option == "--forceall":
            force_all = True
        elif option == "--forcedownload":
            force_download = True
        elif option == "--forceupload":
            force_upload = True
        elif option == "--forceclean":
            force_clean = True
        elif option == "--forcenotify":
            force_notify = True
        elif option == "--simulate":
            simulate = True
        elif option == "--showconfig":
            show_config = True
        elif option == "--showdiag":
            show_diag = True
        elif option == "--live":
            no_live = True
        elif option == "--version":
            steam_appversion = argument
        elif option == "--steamuser":
            CFG.settings['steam']['user'] = argument
        elif option == "--steampassword":
            CFG.settings['steam']['password'] = argument

    # endregion

    LOGGER.log(f"Simulation flag is ENABLED, no action will be executed for real", log_type=LogLevel.LOG_WARNING)

    # region INSTALL
    # install all the dependencies and test them
    if install:
        LOGGER.log("Updating apt sources...", end="")
        if not simulate:
            if sys.platform.startswith('linux'):
                ok = os.system("sudo apt-get update -qq -y > /dev/null 1")
                if ok > 0:
                    LOGGER.log("Dependencies installation failed", log_type=LogLevel.LOG_ERROR, no_date=True)
                    exitcode = errors.APT_UPDATE_FAILED
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
                    exitcode = errors.APT_INSTALL_FAILED
                LOGGER.log("OK", log_type=LogLevel.LOG_SUCCESS, no_date=True)
            elif sys.platform.startswith('win32'):
                ok = os.system("python.exe -m pip install --upgrade pip --no-warn-script-location 1> nul")
                if ok > 0:
                    LOGGER.log("Dependencies installation failed", log_type=LogLevel.LOG_ERROR, no_date=True)
                    exitcode = errors.PYTHON_INSTALLATION_FAILED
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
                    exitcode = errors.AWS_DOWNLOAD_DEPENDENCIES_FAILED
                ok = os.system('unzip -oq ' + CFG.settings['basepath'] + '/awscliv2.zip -d ' + CFG.settings['basepath'])
                if ok > 0:
                    LOGGER.log("Dependencies installation failed", log_type=LogLevel.LOG_ERROR, no_date=True)
                    exitcode = errors.AWS_UNZIP_DEPENDENCIES_FAILED
                ok = os.system('rm ' + CFG.settings['basepath'] + '/awscliv2.zip')
                if ok > 0:
                    LOGGER.log("Dependencies installation failed", log_type=LogLevel.LOG_ERROR, no_date=True)
                    exitcode = errors.AWS_CLEAN_DEPENDENCIES_FAILED
                ok = os.system('sudo ' + CFG.settings['basepath'] + '/aws/install --update')
                if ok > 0:
                    LOGGER.log("Dependencies installation failed", log_type=LogLevel.LOG_ERROR, no_date=True)
                    exitcode = errors.AWS_INSTALL_DEPENDENCIES_FAILED
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
                    exitcode = errors.PYTHON_INSTALL_DEPENDENCIES_FAILED
                LOGGER.log("OK", log_type=LogLevel.LOG_SUCCESS, no_date=True)
            elif sys.platform.startswith('win32'):
                cmd = f"python3 -m pip install -r {CFG.settings['basepath']}\\requirements.txt 1> nul"
                ok = os.system(cmd)
                if ok > 0:
                    LOGGER.log("Dependencies installation failed", log_type=LogLevel.LOG_ERROR, no_date=True)
                    exitcode = errors.PYTHON_INSTALL_DEPENDENCIES_FAILED
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
        os.system('echo "Success" > ' + CFG.settings['basepath'] + '/test_successful.txt')
        ok = AWS_S3.s3_upload_file(CFG.settings['basepath'] + '/test_successful.txt',
                                   'UCB/unity-builds/test_successful.txt')
        if ok != 0:
            LOGGER.log("Error uploading file to S3 UCB/unity-builds. Check the IAM permissions",
                       log_type=LogLevel.LOG_ERROR,
                       no_date=True)
            exitcode = errors.AWS_S3_UPLOAD_TEST_FAILED
        ok = AWS_S3.s3_delete_file('UCB/unity-builds/test_successful.txt')
        if ok != 0:
            LOGGER.log("Error deleting file from S3 UCB/unity-builds. Check the IAM permissions",
                       log_type=LogLevel.LOG_ERROR,
                       no_date=True)
            exitcode = errors.AWS_S3_DELETE_TEST_FAILED
        os.remove(CFG.settings['basepath'] + '/test_successful.txt')
        ok = os.path.exists(CFG.settings['basepath'] + '/test_successful.txt')
        if ok != 0:
            LOGGER.log("Error deleting after connecting to S3", log_type=LogLevel.LOG_ERROR, no_date=True)
            exitcode = errors.AWS_S3_CLEAN_TEST_FAILED
        LOGGER.log("OK", log_type=LogLevel.LOG_SUCCESS, no_date=True)

        LOGGER.log("Testing AWS DynamoDB connection...", end="")
        packages: list = AWS_DDB.get_packages_data()
        if len(packages) > 0:
            ok = 0
        else:
            ok = -1

        if ok != 0:
            LOGGER.log("Error connection to AWS DynamoDB", log_type=LogLevel.LOG_ERROR, no_date=True)
            exitcode = errors.AWS_DDB_CONNECTION_TEST_FAILED
        LOGGER.log("OK", log_type=LogLevel.LOG_SUCCESS, no_date=True)

        LOGGER.log("Installing UCB-steam startup script...", end="")
        if not simulate:
            if sys.platform.startswith('linux'):
                shutil.copyfile(CFG.settings['basepath'] + '/UCB-steam-startup-script.example',
                                CFG.settings['basepath'] + '/UCB-steam-startup-script')
                replace_in_file(CFG.settings['basepath'] + '/UCB-steam-startup-script', '%basepath%',
                                CFG.settings['basepath'])
                ok = os.system(
                    'sudo mv ' + CFG.settings[
                        'basepath'] + '/UCB-steam-startup-script /etc/init.d/UCB-steam-startup-script > /dev/null')
                if ok != 0:
                    LOGGER.log("Error copying UCB-steam startup script file to /etc/init.d",
                               log_type=LogLevel.LOG_ERROR, no_date=True)
                    exitcode = errors.UCB_STARTUP_SCRIPT_INSTALLATION_FAILED
                ok = os.system(
                    'sudo chown root:root /etc/init.d/UCB-steam-startup-script ; sudo chmod 755 /etc/init.d/UCB-steam-startup-script ; sudo systemctl daemon-reload > /dev/null')
                if ok > 0:
                    LOGGER.log("Error setting permission to UCB-steam startup script file",
                               log_type=LogLevel.LOG_ERROR,
                               no_date=True)
                    exitcode = errors.UCB_CHOWN_INSTALLATION_FAILED
                LOGGER.log("OK", log_type=LogLevel.LOG_SUCCESS, no_date=True)
            else:
                LOGGER.log("OS is not Linux", log_type=LogLevel.LOG_SUCCESS, no_date=True)
        else:
            LOGGER.log("Skipped", log_type=LogLevel.LOG_SUCCESS, no_date=True)

        for store in PLUGIN_MANAGER.store_plugins.values():
            store.install(simulate)
        for hook in PLUGIN_MANAGER.hook_plugins.values():
            hook.install(simulate)

        LOGGER.log("Testing UCB connection...", end="")
        UCB_builds_test = UCB.get_last_builds(platform=platform)
        if UCB_builds_test is None:
            LOGGER.log("Error connecting to UCB", log_type=LogLevel.LOG_ERROR, no_date=True)
            exitcode = errors.UCB_CONNECTION_TEST_FAILED
        LOGGER.log("OK", log_type=LogLevel.LOG_SUCCESS, no_date=True)

        for store in PLUGIN_MANAGER.store_plugins.values():
            store.test()
        for hook in PLUGIN_MANAGER.hook_plugins.values():
            hook.test()

        LOGGER.log("Testing email notification...", end="")
        if not no_email:
            str_log = '<b>Result of the UCB-steam script installation:</b>\r\n</br>\r\n</br>'
            str_log = str_log + read_from_file(LOGGER.log_file_path)
            str_log = str_log + '\r\n</br>\r\n</br><font color="GREEN">Everything is set up correctly. Congratulations !</font>'
            AWS_SES_client: PolyAWSSES = PolyAWSSES(CFG.settings['aws']['region'])
            ok = AWS_SES_client.send_email(sender=CFG.settings['email']['from'],
                                           recipients=CFG.settings['email']['recipients'],
                                           title="Steam build notification test",
                                           message=str_log, quiet=True)
            if ok != 0:
                LOGGER.log("Error sending email", log_type=LogLevel.LOG_ERROR, no_date=True)
                exitcode = errors.EMAIL_CONNECTION_TEST_FAILED
            LOGGER.log("OK", log_type=LogLevel.LOG_SUCCESS, no_date=True)
        else:
            LOGGER.log("Not tested (--noemail flag used)", log_type=LogLevel.LOG_WARNING, no_date=True)

        LOGGER.log("Everything is set up correctly. Congratulations !", log_type=LogLevel.LOG_SUCCESS)

        return exitcode
    # endregion

    # region PACKAGES CONFIG
    LOGGER.log(f"Retrieving configuration from DynamoDB (table {CFG.settings['aws']['dynamodbtable']})...", end="")
    exitcode = PACKAGE_MANAGER.load_config(environments=environments)
    LOGGER.log("OK", no_date=True, log_type=LogLevel.LOG_SUCCESS)
    # endregion

    # region SHOW CONFIG
    if exitcode == 0 and show_config:
        LOGGER.log(f"Displaying configuration...")
        LOGGER.log('', no_date=True)

        PACKAGE_MANAGER.print_config(with_diag=False)

        return 0
    # endregion

    # region UCB builds information query
    UCB_all_builds: List[Build] = list()

    # Get all the successful builds from Unity Cloud Build
    if exitcode == 0:
        build_filter = ""
        if platform != "":
            build_filter = f"(Filtering on platform:{platform})"
        if build_filter != "":
            LOGGER.log(f"Retrieving all the builds information from UCB {build_filter}...", end="")
        else:
            LOGGER.log(f"Retrieving all the builds information from UCB...", end="")

        try:
            UCB_all_builds = UCB.get_builds(platform=platform)
        except requests.exceptions.ConnectionError:
            exitcode = errors.UCB_GET_BUILD_ERROR
        except urllib3.exceptions.ProtocolError:
            exitcode = errors.UCB_GET_BUILD_ERROR

        if len(UCB_all_builds) == 0:
            if force_all:
                LOGGER.log("No build available in UCB but process forced to continue (--forceall flag used)",
                           log_type=LogLevel.LOG_WARNING,
                           no_date=True)
            elif force_download:
                LOGGER.log("No build available in UCB but process forced to continue (--forcedownload flag used)",
                           log_type=LogLevel.LOG_WARNING,
                           no_date=True)
            elif show_diag:
                LOGGER.log("No build available in UCB but process forced to continue (--showdiag flag used)",
                           log_type=LogLevel.LOG_WARNING,
                           no_date=True)
            else:
                LOGGER.log("No build available in UCB", log_type=LogLevel.LOG_SUCCESS, no_date=True)
                exitcode = errors.UCB_NO_BUILD_AVAILABLE
        else:
            LOGGER.log("OK", log_type=LogLevel.LOG_SUCCESS, no_date=True)

        # filter on successful builds only
        UCB.display_builds_details()
    # endregion

    # region PACKAGE COMPLETION CHECK
    if exitcode == 0:
        LOGGER.log(f"Compiling UCB data with configuration...", end="")

        # identify the full completion of a package (based on the configuration)
        for package in PACKAGE_MANAGER.packages.values():
            package.update_completion(UCB_all_builds)

        LOGGER.log("OK", no_date=True, log_type=LogLevel.LOG_SUCCESS)
    # endregion

    # region SHOW DIAG
    if exitcode == 0 and show_diag:
        LOGGER.log(f"Displaying diagnostics...")
        LOGGER.log('', no_date=True)

        PACKAGE_MANAGER.print_config(with_diag=True)

        return 0
    # endregion

    if exitcode == 0:
        can_continue = False
        for package in PACKAGE_MANAGER.packages.values():
            if package.complete:
                can_continue = True

        LOGGER.log(" One or more packages complete...", end="")
        if can_continue:
            LOGGER.log("OK", no_date=True, log_type=LogLevel.LOG_SUCCESS)
        elif force_all:
            LOGGER.log(f"Process forced to continue (--forceall flag used)", no_date=True, log_type=LogLevel.LOG_WARNING)
        elif force_download:
            LOGGER.log(f"Process forced to continue (--forcedownload flag used)", no_date=True,
                       log_type=LogLevel.LOG_WARNING)
        else:
            LOGGER.log("At least one package must be complete to proceed to the next step", no_date=True,
                       log_type=LogLevel.LOG_ERROR)
            exitcode = errors.NO_PACKAGE_COMPLETE

    # region DOWNLOAD
    if (exitcode == 0 or force_all or force_download) and not no_download:
        LOGGER.log("--------------------------------------------------------------------------", no_date=True)
        forceTemp: bool = force_all or force_download
        exitcode = PACKAGE_MANAGER.download_builds(force=forceTemp, simulate=simulate, no_s3upload=no_s3upload)
    # endregion

    # region VERSION
    if (exitcode == 0 or force_all or force_download) and not no_download:
        LOGGER.log("--------------------------------------------------------------------------", no_date=True)
        forceTemp: bool = force_all or force_download
        exitcode = PACKAGE_MANAGER.get_version(force=forceTemp, app_version=steam_appversion)
    # endregion

    # region UPLOAD
    if (exitcode == 0 or force_all or force_upload) and not no_upload:
        LOGGER.log("--------------------------------------------------------------------------", no_date=True)
        LOGGER.log("Uploading files to stores...")

        forceTemp: bool = force_all or force_upload
        exitcode = PACKAGE_MANAGER.upload_builds(simulate=simulate, force=forceTemp, app_version=steam_appversion, no_live=no_live,
                                                 stores=stores)
    # endregion

    # region CLEAN
    if (exitcode == 0 or force_all or force_clean) and not no_clean:
        LOGGER.log("--------------------------------------------------------------------------", no_date=True)
        LOGGER.log("Cleaning successfully upload build in UCB...")

        forceTemp: bool = force_all or force_clean
        exitcode = PACKAGE_MANAGER.clean_builds(force=forceTemp, simulate=simulate)
    # endregion

    # region NOTIFY
    if (exitcode == 0 or force_all or force_notify) and not no_notify:
        LOGGER.log("--------------------------------------------------------------------------", no_date=True)
        LOGGER.log("Notify hooks for successfully building process...")

        forceTemp: bool = force_all or force_notify
        exitcode = PACKAGE_MANAGER.notify(force=forceTemp, simulate=simulate, hooks=hooks)
    # end region

    LOGGER.log("--------------------------------------------------------------------------", no_date=True)
    LOGGER.log("All done!", log_type=LogLevel.LOG_SUCCESS)

    return exitcode


if __name__ == "__main__":
    code_ok = 0
    no_shutdown = False
    no_email = False
    try:
        options, arguments = getopt.getopt(sys.argv[1:], "h",
                                           ["help", "nolive", "nodownload", "nos3upload", "noupload", "noclean",
                                            "nonotify",
                                            "noshutdown",
                                            "noemail",
                                            "forceall",
                                            "forcedownload",
                                            "forceupload",
                                            "forceclean",
                                            "forcenotify",
                                            "install", "simulate", "showconfig", "showdiag", "platform=",
                                            "store=",
                                            "hook=",
                                            "environment=",
                                            "version=",
                                            "steamuser=",
                                            "steampassword="])
        for option, argument in options:
            if option == "--noshutdown":
                no_shutdown = True
            elif option == "--noemail":
                no_email = True
            elif option == "--install":
                no_shutdown = True
    except getopt.GetoptError:
        LOGGER.log(log_type=LogLevel.LOG_ERROR, message=f'parameter error: {getopt.GetoptError.msg}')
        print_help()
        code_ok = errors.INVALID_PARAMETERS2

    if code_ok != errors.INVALID_PARAMETERS1 and code_ok != errors.INVALID_PARAMETERS2:
        code_ok = main(sys.argv[1:])
        if not no_shutdown and code_ok != errors.INVALID_PARAMETERS1:
            LOGGER.log("Shutting down computer...")
            os.system("sudo shutdown +3")

    execution_time: float = round((time.time() - start_time), 4)
    LOGGER.log(f"--- Script execution time : {execution_time} seconds ---")
    # close the logfile
    LOGGER.close()
    if code_ok != errors.INVALID_PARAMETERS1 and code_ok != errors.INVALID_PARAMETERS2 and not no_email:
        AWS_SES: PolyAWSSES = PolyAWSSES(CFG.settings['aws']['region'])
        AWS_SES.send_email(sender=CFG.settings['email']['from'], recipients=CFG.settings['email']['recipients'],
                           title="Steam build result",
                           message=read_from_file(LOGGER.log_file_path))

    sys.exit(code_ok)
