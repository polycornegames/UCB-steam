__version__ = "0.32"

import array
import getopt
import os
import shutil
import sys
import time
from pathlib import Path

import libraries
from libraries import AWS, Unity
from libraries import *
from libraries.AWS import *
from libraries.AWS.aws import PolyAWSSES
from libraries.Unity import *
from libraries.common import errors
from libraries.common.libraries import write_in_file, replace_in_file, read_from_file, print_help
from libraries.logger import LogLevel

start_time = time.time()


def main(argv):
    # region INITIAL LOAD
    libraries.load()
    # endregion

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
    force_download_over_max_age = False
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
                                            "forcedownloadovermaxage",
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
        elif option == "--forcedownloadovermaxage":
            force_download_over_max_age = True
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

    # region INIT
    AWS.init()
    Unity.init()
    # endregion

    # region dynamoDB settings retrieval
    if AWS_DDB and CFG.use_dynamodb_for_settings:
        CFG.load_DDB_config()
    # endregion

    # region LOAD MANAGERS
    MANAGERS.load_managers()
    # endregion

    if simulate:
        LOGGER.log(f"Simulation flag is ENABLED, no action will be executed for real", log_type=LogLevel.LOG_WARNING)

    # region INSTALL
    # install all the dependencies and test them
    if install:
        LOGGER.log("Updating apt sources...", end="")
        if not simulate:
            if sys.platform.startswith('linux'):
                ok = os.system("sudo apt-get update -qq -y > /dev/null 1")
                if ok > 0:
                    LOGGER.log("Updating apt failed", log_type=LogLevel.LOG_ERROR, no_date=True)
                    exitcode = errors.APT_UPDATE_FAILED
                LOGGER.log("OK", log_type=LogLevel.LOG_SUCCESS, no_date=True)
            else:
                LOGGER.log("OS is not Linux", log_type=LogLevel.LOG_SUCCESS, no_date=True)
        else:
            LOGGER.log("Skipped", log_type=LogLevel.LOG_SUCCESS, no_date=True)

        LOGGER.log("Installing dependencies...", end="")
        if not simulate:
            if sys.platform.startswith('linux'):
                ok = os.system(
                    "sudo apt-get install -qq -y mc python3-pip git lib32gcc1 python3-requests libsdl2-2.0 > /dev/null")
                ok = os.system(
                    "sudo apt-get install -qq -y mc python3-pip git lib32gcc1 python3-requests libsdl2-2.0 > /dev/null")
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
                ok = os.system(
                    'curl "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o "' + CFG.base_path + '/awscliv2.zip" --silent')
                if ok > 0:
                    LOGGER.log("Dependencies installation failed", log_type=LogLevel.LOG_ERROR, no_date=True)
                    exitcode = errors.AWS_DOWNLOAD_DEPENDENCIES_FAILED
                ok = os.system('unzip -oq ' + CFG.base_path + '/awscliv2.zip -d ' + CFG.base_path)
                if ok > 0:
                    LOGGER.log("Dependencies installation failed", log_type=LogLevel.LOG_ERROR, no_date=True)
                    exitcode = errors.AWS_UNZIP_DEPENDENCIES_FAILED
                ok = os.system('rm ' + CFG.base_path + '/awscliv2.zip')
                if ok > 0:
                    LOGGER.log("Dependencies installation failed", log_type=LogLevel.LOG_ERROR, no_date=True)
                    exitcode = errors.AWS_CLEAN_DEPENDENCIES_FAILED
                ok = os.system('sudo ' + CFG.base_path + '/aws/install --update')
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
                ok = os.system(f"sudo pip3 install -r {CFG.base_path}/requirements.txt > /dev/null")
                if ok > 0:
                    LOGGER.log("Dependencies installation failed", log_type=LogLevel.LOG_ERROR, no_date=True)
                    exitcode = errors.PYTHON_INSTALL_DEPENDENCIES_FAILED
                LOGGER.log("OK", log_type=LogLevel.LOG_SUCCESS, no_date=True)
            elif sys.platform.startswith('win32'):
                cmd = f"python3 -m pip install -r {CFG.base_path}\\requirements.txt 1> nul"
                ok = os.system(cmd)
                if ok > 0:
                    LOGGER.log("Dependencies installation failed", log_type=LogLevel.LOG_ERROR, no_date=True)
                    exitcode = errors.PYTHON_INSTALL_DEPENDENCIES_FAILED
                LOGGER.log("OK", log_type=LogLevel.LOG_SUCCESS, no_date=True)
            else:
                LOGGER.log("OS is neither Windows or Linux", log_type=LogLevel.LOG_ERROR, no_date=True)
        else:
            LOGGER.log("Skipped", log_type=LogLevel.LOG_SUCCESS, no_date=True)

        LOGGER.log("Configuring AWS credentials...")
        if not simulate:
            if not os.path.exists(CFG.home_path + '/.aws'):
                os.mkdir(CFG.home_path + '/.aws')

            LOGGER.log(" Writing AWS config file in " + CFG.home_path + "/.aws/config...", end="")
            write_in_file(CFG.home_path + '/.aws/config',
                          '[default]\r\nregion=' + CFG.aws[
                              'region'] + '\r\noutput=json\r\naws_access_key_id=' +
                          CFG.aws['accesskey'] + '\r\naws_secret_access_key=' + CFG.aws['secretkey'])

            LOGGER.log("OK", log_type=LogLevel.LOG_SUCCESS, no_date=True)
        else:
            LOGGER.log("Skipped", log_type=LogLevel.LOG_SUCCESS, no_date=True)

        LOGGER.log("Testing AWS DynamoDB connection...", end="")
        try:
            packages: list = AWS_DDB.get_packages_data()
            if len(packages) >= 0:
                ok = 0
            else:
                ok = -1
        except Exception as e:
            ok = -1

        if ok != 0:
            LOGGER.log("Error connection to AWS DynamoDB", log_type=LogLevel.LOG_ERROR, no_date=True)
            exitcode = errors.AWS_DDB_CONNECTION_TEST_FAILED
        LOGGER.log("OK", log_type=LogLevel.LOG_SUCCESS, no_date=True)

        LOGGER.log("Installing UCB-steam startup script...", end="")
        if not simulate:
            if sys.platform.startswith('linux'):
                shutil.copyfile(CFG.base_path + '/resources/UCB-steam-startup-script.example',
                                CFG.base_path + '/resources/UCB-steam-startup-script')
                replace_in_file(CFG.base_path + '/resources/UCB-steam-startup-script', '%basepath%',
                                CFG.base_path)
                ok = os.system(
                    'sudo mv ' + CFG.base_path + '/resources/UCB-steam-startup-script /etc/init.d/UCB-steam-startup-script > /dev/null')
                if ok != 0:
                    LOGGER.log("Error copying UCB-steam startup script file to /etc/init.d",
                               log_type=LogLevel.LOG_ERROR, no_date=True)
                    exitcode = errors.UCB_STARTUP_SCRIPT_INSTALLATION_FAILED
                ok = os.system(
                    'sudo chown root:root /etc/init.d/UCB-steam-startup-script ; sudo chmod 755 /etc/init.d/UCB-steam-startup-script ; sudo systemctl enable UCB-steam-startup-script; sudo systemctl daemon-reload > /dev/null')
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

        for store in MANAGERS.plugin_manager.store_plugins.values():
            store.install(simulate)
        for hook in MANAGERS.plugin_manager.hook_plugins.values():
            hook.install(simulate)

        LOGGER.log("Testing UCB connection...", end="")
        UCB_builds_test = UCB.get_last_builds(platform=platform)
        if UCB_builds_test is None:
            LOGGER.log("Error connecting to UCB", log_type=LogLevel.LOG_ERROR, no_date=True)
            exitcode = errors.UCB_CONNECTION_TEST_FAILED
        LOGGER.log("OK", log_type=LogLevel.LOG_SUCCESS, no_date=True)

        for store in MANAGERS.plugin_manager.store_plugins.values():
            store.test()
        for hook in MANAGERS.plugin_manager.hook_plugins.values():
            hook.test()

        LOGGER.log("Testing email notification...", end="")
        if not no_email:
            str_log = '<b>Result of the UCB-steam script installation:</b>\r\n</br>\r\n</br>'
            str_log = str_log + read_from_file(LOGGER.log_file_path)
            str_log = str_log + '\r\n</br>\r\n</br><font color="GREEN">Everything is set up correctly. Congratulations !</font>'
            AWS_SES_client: PolyAWSSES = PolyAWSSES()
            PolyAWSSES.init(aws_region=CFG.aws['region'])
            ok = AWS_SES_client.send_email(sender=CFG.email.sender,
                                           recipients=CFG.email.recipients,
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
    exitcode = MANAGERS.package_manager.load_config(environments=environments, platform=platform)
    # endregion

    # region SHOW CONFIG PACKAGES
    if exitcode == 0 and show_config:
        LOGGER.log(f"Displaying main configuration...")
        CFG.print_config()
        LOGGER.log('', no_date=True)

        LOGGER.log(f"Displaying packages configuration...")
        MANAGERS.package_manager.print_config(with_diag=False)
        LOGGER.log('', no_date=True)

        return 0
    # endregion

    if not CFG.processing_enabled:
        LOGGER.log(f"Processing flag is disabled, nothing will be processed", log_type=LogLevel.LOG_INFO)
        return 0

    iteration: int = 0
    while iteration == 0 or (iteration < 5 and (len(MANAGERS.package_manager.packages_queue) > 0 and not simulate)):
        if iteration > 0:
            exitcode = MANAGERS.package_manager.load_config(environments=environments, platform=platform)

            LOGGER.log(f"Checking if new buildtargets are in the queue...", end="")
        else:
            LOGGER.log(f"Checking if buildtargets are in the queue...", end="")

        LOGGER.log(f"OK ({len(MANAGERS.package_manager.packages_queue)} buildtargets)", log_type=LogLevel.LOG_SUCCESS,
                   no_date=True)
        iteration += 1

        # region DISPLAY FILTERED BUILDS
        if exitcode == 0 and len(MANAGERS.package_manager.filtered_builds) == 0:
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

        # filter on successful builds only
        UCB.display_builds_details()

        # endregion

        # region SHOW DIAG
        if exitcode == 0 and show_diag:
            LOGGER.log(f"Displaying diagnostics...")
            LOGGER.log('', no_date=True)

            MANAGERS.package_manager.print_config(with_diag=True)

            return 0
        # endregion

        if exitcode == 0:
            can_continue = False
            for package in MANAGERS.package_manager.packages.values():
                if package.complete:
                    can_continue = True

            LOGGER.log("One or more packages complete...", end="")
            if can_continue:
                LOGGER.log("OK", no_date=True, log_type=LogLevel.LOG_SUCCESS)
            elif force_all:
                LOGGER.log(f"Process forced to continue (--forceall flag used)", no_date=True,
                           log_type=LogLevel.LOG_WARNING, no_prefix=True)
            elif force_download:
                LOGGER.log(f"Process forced to continue (--forcedownload flag used)", no_date=True,
                           log_type=LogLevel.LOG_WARNING, no_prefix=True)
            else:
                LOGGER.log("At least one package must be complete to proceed to the next step", no_date=True,
                           log_type=LogLevel.LOG_ERROR, no_prefix=True)
                exitcode = errors.NO_PACKAGE_COMPLETE

        # region DOWNLOAD
        if (exitcode == 0 or force_all or force_download) and not no_download:
            LOGGER.log("--------------------------------------------------------------------------", no_date=True)
            MANAGERS.package_manager.prepare_download(force_download=(force_download or CFG.force_download),
                                                      force_over_max_age=force_download_over_max_age,
                                                      debug=CFG.debug)

            exitcode = MANAGERS.package_manager.download_builds(simulate=simulate, no_s3upload=no_s3upload)
        # endregion

        # region VERSION
        if (CFG.check_project_version and (exitcode == 0 or force_all or force_upload)) and not no_upload:
            LOGGER.log("--------------------------------------------------------------------------", no_date=True)
            forceTemp: bool = force_all or force_upload
            exitcode = MANAGERS.package_manager.get_version(force=forceTemp, app_version=steam_appversion)
        # endregion

        # region UPLOAD
        if (exitcode == 0 or force_all or force_upload) and not no_upload:
            LOGGER.log("--------------------------------------------------------------------------", no_date=True)
            LOGGER.log("Uploading files to stores...")

            forceTemp: bool = force_all or force_upload
            exitcode = MANAGERS.package_manager.upload_builds(simulate=simulate, force=forceTemp,
                                                              app_version=steam_appversion,
                                                              no_live=no_live,
                                                              stores=stores, debug=CFG.debug)
        # endregion

        # region NOTIFY
        MANAGERS.package_manager.marked_as_processed()

        if (exitcode == 0 or force_all or force_notify) and not no_notify:
            LOGGER.log("--------------------------------------------------------------------------", no_date=True)
            LOGGER.log("Notify hooks for successfully building process...")

            forceTemp: bool = force_all or force_notify
            exitcode = MANAGERS.package_manager.notify(force=forceTemp, simulate=simulate, hooks=hooks)
        # end region

        # region CLEAN
        if (exitcode == 0 or force_all or force_clean) and not no_clean:
            LOGGER.log("--------------------------------------------------------------------------", no_date=True)
            LOGGER.log("Cleaning successfully upload build in UCB...")

            forceTemp: bool = force_all or force_clean
            exitcode = MANAGERS.package_manager.clean_builds(force=forceTemp, simulate=simulate)
        # endregion

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
                                            "forcedownloadovermaxage",
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
            LOGGER.log(f"Shutting down computer in {CFG.shutdown_delay} minutes...")
            if CFG.shutdown_delay <= 0:
                os.system("sudo shutdown now")
            else:
                os.system(f"sudo shutdown +{CFG.shutdown_delay}")

    execution_time: float = round((time.time() - start_time), 4)
    LOGGER.log(f"--- Script execution time : {execution_time} seconds ---")
    # close the logfile
    LOGGER.close()
    if code_ok != errors.INVALID_PARAMETERS1 and code_ok != errors.INVALID_PARAMETERS2 and not no_email:
        AWS_SES: PolyAWSSES = PolyAWSSES()
        PolyAWSSES.init(aws_region=CFG.aws['region'])
        AWS_SES.send_email(sender=CFG.email.sender, recipients=CFG.email.recipients,
                           title="Steam build result",
                           message=read_from_file(LOGGER.log_file_path))

    sys.exit(code_ok)
