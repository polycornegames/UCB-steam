__version__ = "0.31"

import array
import getopt
import glob
import os
import shutil
import stat
import sys
import time
import urllib.request
from datetime import datetime
from typing import Dict, List
from zipfile import ZipFile

import requests
import vdf

from librairies import LOGGER, CFG
from librairies.UCB.UCB import PolyUCB
from librairies.UCB.classes import Build, UCBBuildStatus
from librairies.aws import PolyAWSS3, PolyAWSDynamoDB, PolyAWSSES
from librairies.common.classes import Package
from librairies.common.libraries import write_in_file, replace_in_file, read_from_file, load_packages_config
from librairies.libraries import PolyBitBucket, Hook
from librairies.logger import LogLevel

start_time = time.time()


class BitBucketHook(Hook):
    bitbucket_connection: PolyBitBucket

    def __init__(self, name: str, notified: bool = False):
        super().__init__(name, notified)

    def notify(self):
        self.bitbucket_connection = PolyBitBucket(bitbucket_username=CFG.settings['bitbucket']['username'],
                                                  bitbucket_app_password=CFG.settings['bitbucket']['app_password'],
                                                  bitbucket_cloud=True,
                                                  bitbucket_workspace=CFG.settings['bitbucket']['workspace'],
                                                  bitbucket_repository=CFG.settings['bitbucket']['repository'])
        self.bitbucket_connection.trigger_pipeline(
            self.parameters['branch'],
            self.parameters['pipeline'])


# region HELPER LIBRARY
def print_help():
    print(
        f"UCB-steam.py [--platform=(standalonelinux64, standaloneosxuniversal, standalonewindows64)] [--environment=(environment1, environment2, ...)] [--store=(store1,store2,...)] [--nolive] [--force] [--version=<version>] [--install] [--nodownload] [--nos3upload] [--noupload] [--noclean] [--noshutdown] [--noemail] [--simulate] [--showconfig | --showdiag] [--steamuser=<steamuser>] [--steampassword=<steampassword>]")


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

        for store, build_targets in package.stores.items():
            LOGGER.log(f'  store: {store}', no_date=True)
            for build_target_id, build_target in build_targets.items():
                LOGGER.log(f'    buildtarget: {build_target_id}', no_date=True)
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

    # region STEAM AND BUTLER VARIABLES

    butler_dir_path = f'{CFG.settings["basepath"]}/Butler'
    butler_exe_path = ''
    if sys.platform.startswith('linux'):
        butler_exe_path = f'{butler_dir_path}/butler'
    elif sys.platform.startswith('win32'):
        butler_exe_path = f'{butler_dir_path}/butler.exe'
    butler_config_dir_path = f'{CFG.settings["homepath"]}/.config/ich'
    butler_config_file_path = f'{butler_config_dir_path}/butler_creds'
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
        AWS_S3: PolyAWSS3 = PolyAWSS3(aws_region=CFG.settings['aws']['region'])
        ok = os.system('echo "Success" > ' + CFG.settings['basepath'] + '/test_successful.txt')
        if ok != 0:
            LOGGER.log("Creating temp file for connection test to S3", log_type=LogLevel.LOG_ERROR, no_date=True)
            return 300
        ok = AWS_S3.s3_upload_file(CFG.settings['basepath'] + '/test_successful.txt', CFG.settings['aws']['s3bucket'],
                                   'UCB/steam-parameters/test_successful.txt')
        if ok != 0:
            LOGGER.log("Error uploading file to S3 UCB/steam-parameters. Check the IAM permissions",
                       log_type=LogLevel.LOG_ERROR,
                       no_date=True)
            return 301
        ok = AWS_S3.s3_delete_file('UCB/steam-parameters/test_successful.txt', CFG.settings['aws']['s3bucket'])
        if ok != 0:
            LOGGER.log("Error deleting file from S3 UCB/steam-parameters. Check the IAM permissions",
                       log_type=LogLevel.LOG_ERROR,
                       no_date=True)
            return 302
        ok = AWS_S3.s3_upload_file(CFG.settings['basepath'] + '/test_successful.txt', CFG.settings['aws']['s3bucket'],
                                   'UCB/unity-builds/test_successful.txt')
        if ok != 0:
            LOGGER.log("Error uploading file to S3 UCB/unity-builds. Check the IAM permissions",
                       log_type=LogLevel.LOG_ERROR,
                       no_date=True)
            return 303
        ok = AWS_S3.s3_delete_file('UCB/unity-builds/test_successful.txt', CFG.settings['aws']['s3bucket'])
        if ok != 0:
            LOGGER.log("Error deleting file from S3 UCB/unity-builds. Check the IAM permissions",
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
        AWS_DDB: PolyAWSDynamoDB = PolyAWSDynamoDB(aws_region=CFG.settings['aws']['region'])
        packages: Dict[str, Package] = AWS_DDB.get_packages_data()
        if len(packages.keys()) > 0:
            ok = 0

        if ok != 0:
            LOGGER.log("Error connection to AWS DynamoDB", log_type=LogLevel.LOG_ERROR, no_date=True)
            return 304
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
                    return 310
                ok = os.system(
                    'sudo chown root:root /etc/init.d/UCB-steam-startup-script ; sudo chmod 755 /etc/init.d/UCB-steam-startup-script ; sudo systemctl daemon-reload > /dev/null')
                if ok > 0:
                    LOGGER.log("Error setting permission to UCB-steam startup script file", log_type=LogLevel.LOG_ERROR,
                               no_date=True)
                    return 311
                LOGGER.log("OK", log_type=LogLevel.LOG_SUCCESS, no_date=True)
            else:
                LOGGER.log("OS is not Linux", log_type=LogLevel.LOG_SUCCESS, no_date=True)
        else:
            LOGGER.log("Skipped", log_type=LogLevel.LOG_SUCCESS, no_date=True)

        LOGGER.log("Creating folder structure for Steamworks...", end="")
        if not simulate:
            if not os.path.exists(steam_dir_path):
                os.mkdir(steam_dir_path)
            if not os.path.exists(steam_build_path):
                os.mkdir(steam_build_path)
            if not os.path.exists(f"{steam_dir_path}/output"):
                os.mkdir(f"{steam_dir_path}/output")
            if not os.path.exists(f"{steam_dir_path}/scripts"):
                os.mkdir(f"{steam_scripts_path}")
            if not os.path.exists(f"{steam_dir_path}/steamcmd"):
                os.mkdir(f"{steam_dir_path}/steamcmd")
            if not os.path.exists(f"{steam_dir_path}/steam-sdk"):
                os.mkdir(f"{steam_dir_path}/steam-sdk")
            LOGGER.log("OK", log_type=LogLevel.LOG_SUCCESS, no_date=True)
        else:
            LOGGER.log("Skipped", log_type=LogLevel.LOG_SUCCESS, no_date=True)

        LOGGER.log("Testing Bitbucket connection...", end="")
        BITBUCKET: PolyBitBucket = PolyBitBucket(bitbucket_username=CFG.settings['bitbucket']['username'],
                                                 bitbucket_app_password=CFG.settings['bitbucket']['app_password'],
                                                 bitbucket_cloud=True,
                                                 bitbucket_workspace=CFG.settings['bitbucket']['workspace'],
                                                 bitbucket_repository=CFG.settings['bitbucket']['repository'])

        if not BITBUCKET.connect():
            LOGGER.log("Error connecting to Bitbucket", log_type=LogLevel.LOG_ERROR, no_date=True)
            return 45

        LOGGER.log("OK", log_type=LogLevel.LOG_SUCCESS, no_date=True)

        LOGGER.log("Testing UCB connection...", end="")
        UCB: PolyUCB = PolyUCB(unity_org_id=CFG.settings['unity']['org_id'],
                               unity_project_id=CFG.settings['unity']['project_id'],
                               unity_api_key=CFG.settings['unity']['api_key'])
        UCB_builds_test = UCB.get_last_builds(platform=platform)
        if UCB_builds_test is None:
            LOGGER.log("Error connecting to UCB", log_type=LogLevel.LOG_ERROR, no_date=True)
            return 21
        LOGGER.log("OK", log_type=LogLevel.LOG_SUCCESS, no_date=True)

        LOGGER.log("Downloading Steamworks SDK...", end="")
        if not simulate:
            if not os.path.exists(f"{steam_dir_path}/steamcmd/linux32/steamcmd"):
                ok = AWS_S3.s3_download_directory("UCB/steam-sdk", CFG.settings['aws']['s3bucket'],
                                                  f"{CFG.settings['basepath']}/steam-sdk")
                if ok != 0:
                    LOGGER.log("Error getting files from S3", log_type=LogLevel.LOG_ERROR, no_date=True)
                    return 22

                shutil.copytree(f"{CFG.settings['basepath']}/steam-sdk/builder_linux", f"{steam_dir_path}/steamcmd",
                                dirs_exist_ok=True)
                st = os.stat(steam_exe_path)
                os.chmod(steam_exe_path, st.st_mode | stat.S_IEXEC)
                st = os.stat(f"{steam_dir_path}/steamcmd/linux32/steamcmd")
                os.chmod(f"{steam_dir_path}/steamcmd/linux32/steamcmd", st.st_mode | stat.S_IEXEC)
                shutil.rmtree(f"{CFG.settings['basepath']}/steam-sdk")
                LOGGER.log("OK", log_type=LogLevel.LOG_SUCCESS, no_date=True)
            else:
                LOGGER.log("OK (dependencie already met)", log_type=LogLevel.LOG_SUCCESS, no_date=True)
        else:
            LOGGER.log("Skipped", log_type=LogLevel.LOG_SUCCESS, no_date=True)

        LOGGER.log("Testing Steam connection...", end="")
        ok = os.system(
            f'''{steam_exe_path} +login "{CFG.settings['steam']['user']}" "{CFG.settings['steam']['password']}" +quit''')
        if ok != 0:
            LOGGER.log("Error connecting to Steam", log_type=LogLevel.LOG_ERROR, no_date=True)
            return 23
        LOGGER.log("OK", log_type=LogLevel.LOG_SUCCESS, no_date=True)

        LOGGER.log("Creating folder structure for Butler...", end="")
        if not simulate:
            if not os.path.exists(f'{CFG.settings["homepath"]}/.config'):
                os.mkdir(f'{CFG.settings["homepath"]}/.config')
            if not os.path.exists(butler_config_dir_path):
                os.mkdir(butler_config_dir_path)

            if not os.path.exists(butler_dir_path):
                os.mkdir(butler_dir_path)

            LOGGER.log("OK", log_type=LogLevel.LOG_SUCCESS, no_date=True)
        else:
            LOGGER.log("Skipped", log_type=LogLevel.LOG_SUCCESS, no_date=True)

        LOGGER.log("Downloading Butler...", end="")
        if not simulate:
            if not os.path.exists(butler_exe_path):
                butler_url = ''
                zip_path = ''
                if sys.platform.startswith('linux'):
                    butler_url = 'https://broth.itch.ovh/butler/linux-amd64/LATEST/archive/default'
                    zip_path = f'{butler_dir_path}/butler-linux-amd64.zip'
                elif sys.platform.startswith('win32'):
                    butler_url = 'https://broth.itch.ovh/butler/windows-amd64/LATEST/archive/default'
                    zip_path = f'{butler_dir_path}/butler-windows-amd64.zip'

                request = requests.get(butler_url, allow_redirects=True)
                open(zip_path, 'wb').write(request.content)

                if not os.path.exists(zip_path):
                    LOGGER.log("Error downloading Butler", log_type=LogLevel.LOG_ERROR, no_date=True)
                    return 24

                unzipped = 1
                with ZipFile(zip_path, "r") as zipObj:
                    zipObj.extractall(butler_dir_path)
                    unzipped = 0

                if unzipped != 0:
                    LOGGER.log("Error unzipping Butler", log_type=LogLevel.LOG_ERROR, no_date=True)
                    return 23

                st = os.stat(butler_exe_path)
                os.chmod(butler_exe_path, st.st_mode | stat.S_IEXEC)

                LOGGER.log("OK", log_type=LogLevel.LOG_SUCCESS, no_date=True)
            else:
                LOGGER.log("OK (dependencie already met)", log_type=LogLevel.LOG_SUCCESS, no_date=True)
        else:
            LOGGER.log("Skipped", log_type=LogLevel.LOG_SUCCESS, no_date=True)

        LOGGER.log("Setting up Butler...", end="")
        if not simulate:
            write_in_file(butler_config_file_path, CFG.settings['butler']['apikey'])
            if not os.path.exists(butler_config_file_path):
                LOGGER.log("Error setting up Butler", log_type=LogLevel.LOG_ERROR, no_date=True)
                return 25
        LOGGER.log("OK", log_type=LogLevel.LOG_SUCCESS, no_date=True)

        LOGGER.log("Testing Butler connection...", end="")
        cmd = f'{butler_exe_path} status {CFG.settings["butler"]["org"]}/{CFG.settings["butler"]["project"]} 1> nul'
        ok = os.system(cmd)
        if ok != 0:
            LOGGER.log("Error connecting to Butler", log_type=LogLevel.LOG_ERROR, no_date=True)
            return 23
        LOGGER.log("OK", log_type=LogLevel.LOG_SUCCESS, no_date=True)

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
                return 35
            LOGGER.log("OK", log_type=LogLevel.LOG_SUCCESS, no_date=True)
        else:
            LOGGER.log("Not tested (--noemail flag used)", log_type=LogLevel.LOG_WARNING, no_date=True)

        LOGGER.log("Everything is set up correctly. Congratulations !", log_type=LogLevel.LOG_SUCCESS)

        return 0
    # endregion

    # region AWS INIT
    AWS_S3: PolyAWSS3 = PolyAWSS3(CFG.settings['aws']['region'])
    AWS_DDB: PolyAWSDynamoDB = PolyAWSDynamoDB(aws_region=CFG.settings['aws']['region'],
                                               dynamodb_table=CFG.settings['aws']['dynamodbtable'])
    # endregion

    # region PACKAGES CONFIG
    LOGGER.log(f"Retrieving configuration from DynamoDB (table {CFG.settings['aws']['dynamodbtable']})...", end="")
    CFG_packages = load_packages_config(config=CFG, environments=environments)
    LOGGER.log("OK", no_date=True, log_type=LogLevel.LOG_SUCCESS)
    # endregion

    # region SHOW CONFIG
    if show_config:
        LOGGER.log(f"Displaying configuration...")
        LOGGER.log('', no_date=True)

        print_config(packages=CFG_packages)

        return 0
    # endregion

    # region UCB builds information query
    # Get all the successful builds from Unity Cloud Build
    build_filter = ""
    if platform != "":
        build_filter = f"(Filtering on platform:{platform})"
    if build_filter != "":
        LOGGER.log(f"Retrieving all the builds information from UCB {build_filter}...", end="")
    else:
        LOGGER.log(f"Retrieving all the builds information from UCB...", end="")

    UCB: PolyUCB = PolyUCB(unity_org_id=CFG.settings['unity']['org_id'],
                           unity_project_id=CFG.settings['unity']['project_id'],
                           unity_api_key=CFG.settings['unity']['api_key'])

    UCB_all_builds: List[Build] = UCB.get_builds(platform=platform)
    if len(UCB_all_builds) == 0:
        if force:
            LOGGER.log("No build available in UCB but process forced to continue (--force flag used)",
                       log_type=LogLevel.LOG_WARNING,
                       no_date=True)
        elif show_diag:
            LOGGER.log("No build available in UCB but process forced to continue (--showdiag flag used)",
                       log_type=LogLevel.LOG_WARNING,
                       no_date=True)
        else:
            LOGGER.log("No build available in UCB", log_type=LogLevel.LOG_SUCCESS, no_date=True)
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
    # identify completed builds
    LOGGER.log(f"Compiling UCB data with configuration...", end="")
    for build in UCB_all_builds:
        for package_name, package in CFG_packages.items():
            package.attach_build(build_target_id=build.build_target_id, build=build)
            if build.status == UCBBuildStatus.SUCCESS:
                package.set_build_target_completion(build_target_id=build.build_target_id, complete=True)

    # identify the full completion of a package (based on the configuration)
    for package_name, package in CFG_packages.items():
        package.update_completion()

    LOGGER.log("OK", no_date=True, log_type=LogLevel.LOG_SUCCESS)
    # endregion

    # region SHOW DIAG
    if show_diag:
        LOGGER.log(f"Displaying diagnostics...")
        LOGGER.log('', no_date=True)

        print_config(packages=CFG_packages, with_diag=True)

        return 0
    # endregion

    can_continue = False
    for package_name, package in CFG_packages.items():
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
        LOGGER.log("Downloading build from UCB...")

        already_downloaded_build_targets: List[str] = list()
        for package_name, package in CFG_packages.items():
            if package.complete:
                build_targets = package.get_build_targets()
                for build_target in build_targets:
                    if not already_downloaded_build_targets.__contains__(build_target.name):
                        # store the data necessary for the next steps
                        build_os_path = f"{steam_build_path}/{build_target.name}"
                        last_built_revision_path = f"{steam_build_path}/{build_target.name}_lastbuiltrevision.txt"
                        last_built_revision: str = ""
                        if os.path.exists(last_built_revision_path):
                            last_built_revision = read_from_file(last_built_revision_path)

                        if build_target.build is None:
                            LOGGER.log(" Missing build object", log_type=LogLevel.LOG_ERROR)
                            return 5

                        LOGGER.log(f" Preparing {build_target.name}")
                        if build_target.build.number == "":
                            LOGGER.log(" Missing builds field", log_type=LogLevel.LOG_ERROR, no_date=True)
                            return 6

                        if build_target.build.date_finished == datetime.min:
                            LOGGER.log(" The build seems to be a failed one", log_type=LogLevel.LOG_ERROR, no_date=True)
                            return 7

                        if build_target.build.last_built_revision == "":
                            LOGGER.log(" Missing builds field", log_type=LogLevel.LOG_ERROR, no_date=True)
                            return 13

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
                            if time_diff_in_minute > CFG.settings['unity']['build_max_age']:
                                if force:
                                    LOGGER.log(" Process forced to continue (--force flag used)",
                                               log_type=LogLevel.LOG_WARNING,
                                               no_date=True)
                                else:
                                    LOGGER.log(
                                        f" The build is too old (max {str(CFG.settings['unity']['build_max_age'])} min). Try using --force",
                                        log_type=LogLevel.LOG_ERROR,
                                        no_date=True)
                                    return 8
                            else:
                                LOGGER.log(f"OK", log_type=LogLevel.LOG_SUCCESS, no_date=True)

                            # store the lastbuiltrevision in a txt file for diff check
                            if not simulate:
                                if os.path.exists(last_built_revision_path):
                                    os.remove(last_built_revision_path)
                                write_in_file(last_built_revision_path,
                                              build_target.build.last_built_revision)

                            zipfile = f"{CFG.settings['basepath']}/ucb{build_target.name}.zip"

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

                            LOGGER.log(f'  Extracting the zip file in {build_os_path}...', end="")
                            if not simulate:
                                unzipped = 1
                                with ZipFile(zipfile, "r") as zipObj:
                                    zipObj.extractall(build_os_path)
                                    unzipped = 0
                                    LOGGER.log("OK", log_type=LogLevel.LOG_SUCCESS, no_date=True)
                                if unzipped != 0:
                                    LOGGER.log(f'Error unzipping {zipfile} to {build_os_path}',
                                               log_type=LogLevel.LOG_ERROR,
                                               no_date=True)
                                    return 56
                            else:
                                LOGGER.log("OK", log_type=LogLevel.LOG_SUCCESS, no_date=True)

                            if not no_s3upload:
                                s3path = f'UCB/unity-builds/{package_name}/ucb{build_target.name}.zip'
                                LOGGER.log(f'  Uploading copy to S3 {s3path} ...', end="")
                                if not simulate:
                                    ok = AWS_S3.s3_upload_file(zipfile, CFG.settings['aws']['s3bucket'], s3path)
                                else:
                                    ok = 0

                                if ok != 0:
                                    LOGGER.log(
                                        f'Error uploading file "ucb{build_target.name}.zip" to AWS {s3path}. Check the IAM permissions',
                                        log_type=LogLevel.LOG_ERROR, no_date=True)
                                    return 9
                                LOGGER.log("OK", log_type=LogLevel.LOG_SUCCESS, no_date=True)

                        # let's make sure that we'll not download the zip file twice
                        already_downloaded_build_targets.append(build_target.name)
    # endregion

    # region VERSION
    LOGGER.log("--------------------------------------------------------------------------", no_date=True)
    LOGGER.log("Getting version...")
    version_found: bool = False
    already_versioned_build_targets: List[str] = list()
    for package_name, package in CFG_packages.items():
        if package.complete:
            build_targets = package.get_build_targets()
            for build_target in build_targets:
                if not already_versioned_build_targets.__contains__(build_target.name):
                    # let's make sure that we'll not extract the version twice
                    already_versioned_build_targets.append(build_target.name)

                    build_os_path = f"{steam_build_path}/{build_target.name}"

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

        for package_name, package in CFG_packages.items():
            package.uploaded = False

        # region STEAM
        for package_name, package in CFG_packages.items():
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
                        build_path = f"{steam_build_path}/{build_target_id}"

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
        for package_name, package in CFG_packages.items():
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
        LOGGER.log("Cleaning successfully upload build in UCB...")

        already_cleaned_build_targets: List[str] = list()
        # let's remove the build successfully uploaded to Steam or Butler from UCB
        # clean only the packages that are successful
        for package_name, package in CFG_packages.items():
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
    for package_name, package in CFG_packages.items():
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
