__version__ = "0.31"

import copy
import getopt
import glob
import logging
import os
import re
import shutil
import stat
import sys
import time
import urllib.request
from datetime import datetime
from enum import Enum
from zipfile import ZipFile
from pprint import pprint

import boto3
from boto3.dynamodb.conditions import Key, Attr
import requests
import vdf
import yaml
from botocore.exceptions import ClientError
from colorama import Fore, Style
from typing import Dict, TypedDict, List

start_time = time.time()

LOG_ERROR = 0
LOG_WARNING = 1
LOG_INFO = 2
LOG_SUCCESS = 3

global DEBUG_FILE
global DEBUG_FILE_NAME

global CFG


# region CLASSES
class Store(Enum):
    STEAM = 1
    ITCH = 2


class UCBBuildStatus(Enum):
    SUCCESS = 1
    QUEUED = 2
    SENTTOBUILDER = 3
    STARTED = 4
    RESTARTED = 5
    FAILURE = 6
    CANCELED = 7
    UNKNOWN = 8


class Build:
    number: int
    UID: str
    build_target_id: str
    status: UCBBuildStatus
    date_finished: datetime
    download_link: str
    complete: bool
    platform: str
    UCB_object: dict

    def __init__(self, number: int, uid: str, build_target_id: str, status: UCBBuildStatus, date_finished: datetime,
                 download_link: str, platform: str, complete: bool = False, UCB_object=None):
        self.number = number
        self.UID = uid
        self.build_target_id = build_target_id
        self.status = status
        self.date_finished: date_finished
        self.download_link: download_link
        self.platform = platform
        self.complete = complete
        self.UCB_object = UCB_object


class BuildTarget:
    name: str
    build: Build
    complete: bool
    parameters: Dict[str, str]

    def __init__(self, name: str, build: Build = None, complete: bool = False):
        self.name = name
        self.build = build
        self.complete = complete
        self.parameters = dict()


class Package:
    name: str
    complete: bool
    uploaded: bool
    store: Store
    build_targets: Dict[str, BuildTarget]

    def __init__(self, name: str, store: Store, complete: bool = False, uploaded: bool = False):
        self.name = name
        self.store = store
        self.complete = complete
        self.uploaded = uploaded
        self.build_targets = dict()


# endregion

# region UNITY_LIBRARY


def api_url():
    global CFG
    return 'https://build-api.cloud.unity3d.com/api/v1/orgs/{}/projects/{}'.format(CFG['unity']['org_id'],
                                                                                   CFG['unity']['project_id'])


def headers():
    global CFG
    return {'Authorization': 'Basic {}'.format(CFG['unity']['api_key'])}


def create_new_build_target(data, branch, user):
    name_limit = 64 - 17 - len(user)
    name = re.sub("[^0-9a-zA-Z]+", "-", branch)[0:name_limit]

    data['name'] = 'Autobuild of {} by {}'.format(name, user)
    data['settings']['scm']['branch'] = branch

    url = '{}/buildtargets'.format(api_url())
    response = requests.post(url, headers=headers(), json=data)

    if not response.ok:
        logging.error("Creating build target " + data['name'] + " failed", response.text)

    info = response.json()
    return info['buildtargetid'], data['name']


def delete_build_target(buildtargetid):
    url = '{}/buildtargets/{}'.format(api_url(), buildtargetid)
    requests.delete(url, headers=headers())


def start_build(buildtargetid):
    url = '{}/buildtargets/{}/builds'.format(api_url(), buildtargetid)
    data = {'clean': True}
    requests.post(url, headers=headers(), json=data)


def create_build_url(buildtarget_id, build_number):
    global CFG
    return 'https://developer.cloud.unity3d.com/build/orgs/{}/projects/{}/buildtargets/{}/builds/{}/log/compact/'.format(
        CFG['unity']['org_id'], CFG['unity']['project_id'], buildtarget_id, build_number
    )


def get_last_builds(branch="", platform="") -> List[Build]:
    url = '{}/buildtargets?include_last_success=true'.format(api_url())
    response = requests.get(url, headers=headers())

    data_temp = []

    if not response.ok:
        log(f"Getting build template failed: {response.text}", logtype=LOG_ERROR)
        return data_temp

    data = response.json()
    data_temp = copy.deepcopy(data)
    # let's filter the result on the requested branch only
    for i in reversed(range(0, len(data))):
        build = data[i]

        # identify if the build is successfull
        if "builds" not in build:
            # log(f"Missing builds field for {build["buildtargetid"]}", type=LOG_ERROR)
            data_temp.pop(i)
            continue

        # filter on branch
        if branch != "":
            if not build['buildtargetid'] is None:
                # the branch name is at the beginning of the build target name (ex: beta-windows-64bit)
                tabtemp = build['buildtargetid'].split("-")
                if len(tabtemp) > 0:
                    if tabtemp[0] != branch:
                        # the branch name is different: remove the build from the result
                        data_temp.pop(i)
                        continue
                else:
                    log(f"The name of the branch was not detected in {build['buildtargetid']}", logtype=LOG_ERROR)
                    data_temp.pop(i)
                    continue
            else:
                log(f"The buildtargetid was not detected", logtype=LOG_ERROR)
                data_temp.pop(i)
                continue

        # filter on platform
        if platform != "":
            if not build['platform'] is None:
                if build['platform'] != platform:
                    # the branch name is different: remove the build from the result
                    data_temp.pop(i)
                    continue
            else:
                log(f"The platform was not detected", logtype=LOG_ERROR)
                data_temp.pop(i)
                continue

    final_data: List[Build] = list()
    for build in data_temp:
        build_obj = Build(build['build'], build['buildGUID'], build['buildtargetid'], build['buildStatus'],
                          build['finished'], build['links']['download_primary']['href'], build['platform'],
                          UCB_object=build)
        final_data.append(build_obj)

    return final_data


def get_all_builds(build_target: str = "", platform: str = "") -> List[Build]:
    url = '{}/buildtargets/_all/builds'.format(api_url())
    response = requests.get(url, headers=headers())

    data_temp = []

    if not response.ok:
        log(f"Getting build template failed: {response.text}", logtype=LOG_ERROR)
        return data_temp

    data = response.json()
    data_temp = copy.deepcopy(data)
    # let's filter the result on the requested branch only
    for i in reversed(range(0, len(data))):
        build = data[i]

        # identify if the build is successfull
        if "build" not in build:
            # log(f"Missing build field for {build["build"]}", type=LOG_ERROR)
            data_temp.pop(i)
            continue

        # filter on branch
        if build_target != "":
            if build['buildtargetid'] is None:
                if build['buildtargetid'] != build_target:
                    data_temp.pop(i)
                    continue
            else:
                log(f"The buildtargetid was not detected", logtype=LOG_ERROR)
                data_temp.pop(i)
                continue

        # filter on platform
        if platform != "":
            if not build['platform'] is None:
                if build['platform'] != platform:
                    # the branch name is different: remove the build from the result
                    data_temp.pop(i)
                    continue
            else:
                log(f"The platform was not detected", logtype=LOG_ERROR)
                data_temp.pop(i)
                continue

    final_data: List[Build] = list()
    for build in data_temp:
        build_obj = Build(build['build'], build['buildGUID'], build['buildtargetid'], build['buildStatus'],
                          build['finished'], build['links']['download_primary']['href'], build['platform'],
                          UCB_object=build)
        final_data.append(build_obj)

    return final_data


def delete_build(buildtargetid, build):
    deleted = True
    url = '{}/artifacts/delete'.format(api_url())

    data = {'builds': [{"buildtargetid": buildtargetid, "build": int(build)}]}

    response = requests.post(url, headers=headers(), json=data)

    if not response.ok:
        deleted = False
        log(f"Deleting build target failed: {response.text}", logtype=LOG_ERROR)

    return deleted


# endregion

# region FILE LIBRARY
def replace_in_file(file, haystack, needle):
    # read input file
    fin = open(file, "rt")
    # read file contents to string
    data = fin.read()
    # replace all occurrences of the required string
    data = data.replace(str(haystack), str(needle))
    # close the input file
    fin.close()
    # open the input file in write mode
    fin = open(file, "wt")
    # overrite the input file with the resulting data
    fin.write(data)
    # close the file
    fin.close()


def write_in_file(file, data):
    # open the input file in write mode
    fin = open(file, "wt")
    # overrite the input file with the resulting data
    fin.write(data)
    # close the file
    fin.close()


def read_from_file(file):
    # read input file
    fin = open(file, "rt")
    # read file contents to string
    data = fin.read()
    # close the input file
    fin.close()
    return data


# endregion

# region EMAIL LIBRARY
def send_email(sender, recipients, title, message):
    global CFG
    client = boto3.client("ses", region_name=CFG['aws']['region'])
    try:
        # Provide the contents of the email.
        response = client.send_email(
            Destination={
                'ToAddresses': recipients
            },
            Message={
                'Body': {
                    'Html': {
                        'Charset': 'UTF-8',
                        'Data': message,
                    },
                    'Text': {
                        'Charset': 'UTF-8',
                        'Data': message,
                    },
                },
                'Subject': {
                    'Charset': 'UTF-8',
                    'Data': title,
                },
            },
            Source=sender,
        )
    # Display an error if something goes wrong.
    except ClientError as e:
        log(e.response['Error']['Message'], logtype=LOG_ERROR)
        return 461
    else:
        log("Email sent! Message ID:"),
        log(response['MessageId'])
        return 0


# endregion

# region S3 LIBRARY
def s3_download_file(file, bucket, destination):
    global CFG
    client = boto3.client("s3", region_name=CFG['aws']['region'])
    try:
        # Provide the file information to upload.
        response = client.download_file(
            Filename=destination,
            Bucket=bucket,
            Key=file,
        )
        return 0
    # Display an error if something goes wrong.
    except ClientError as e:
        log(e.response['Error']['Message'], logtype=LOG_ERROR)
        return 440


def s3_download_directory(directory, bucket_name, destination):
    global CFG
    client = boto3.client("s3", region_name=CFG['aws']['region'])
    s3 = boto3.resource("s3")
    try:
        bucket = s3.Bucket(bucket_name)
        for obj in bucket.objects.filter(Prefix=directory):
            target = obj.key if destination is None \
                else os.path.join(destination, os.path.relpath(obj.key, directory))
            if not os.path.exists(os.path.dirname(target)):
                os.makedirs(os.path.dirname(target))
            if obj.key[-1] == '/':
                continue
            response = client.download_file(
                Filename=target,
                Bucket=bucket_name,
                Key=obj.key,
            )
        return 0
    # Display an error if something goes wrong.
    except ClientError as e:
        log(e.response['Error']['Message'], logtype=LOG_ERROR)
        return 440


def s3_upload_file(filetoupload, bucket_name, destination):
    global CFG
    client = boto3.client("s3", region_name=CFG['aws']['region'])
    try:
        response = client.put_object(
            Bucket=bucket_name,
            Key=destination,
            Body=open(filetoupload, 'rb')
        )

        return 0
    # Display an error if something goes wrong.
    except ClientError as e:
        log(e.response['Error']['Message'], logtype=LOG_ERROR)
        return 450


def s3_delete_file(bucket_name, filetodelete):
    global CFG
    client = boto3.client("s3", region_name=CFG['aws']['region'])
    try:
        response = client.put_object(
            Bucket=bucket_name,
            Key=filetodelete
        )

        return 0
    # Display an error if something goes wrong.
    except ClientError as e:
        log(e.response['Error']['Message'], logtype=LOG_ERROR)
        return 460


# endregion

# region DYNAMODB LIBRARY
def get_build_target(build_target_id, dynamodb=None):
    global CFG
    if not dynamodb:
        dynamodb = boto3.resource('dynamodb', region_name=CFG['aws']['region'])

    table = dynamodb.Table('UCB-Packages')

    try:
        response = table.get_item(Key={'id': build_target_id})
    except ClientError as e:
        print(e.response['Error']['Message'])
    else:
        return response['Item']


def get_build_targets(package, dynamodb=None):
    global CFG
    if not dynamodb:
        dynamodb = boto3.resource('dynamodb', region_name=CFG['aws']['region'])

    table = dynamodb.Table('UCB-Packages')

    try:
        response = table.query(
            KeyConditionExpression=Key('steam.package').eq(package) | Key('butler.package').eq(package)
        )
    except ClientError as e:
        print(e.response['Error']['Message'])
    else:
        return response['Item']


def get_packages(dynamodb=None):
    global CFG
    if not dynamodb:
        dynamodb = boto3.resource('dynamodb', region_name=CFG['aws']['region'])

    table = dynamodb.Table('UCB-Packages')

    try:
        response = table.scan(
            ProjectionExpression="id, steam, butler"
        )
        data = response['Items']
        while 'LastEvaluatedKey' in response:
            response = table.scan(ExclusiveStartKey=response['LastEvaluatedKey'])
            data.extend(response['Items'])

        packages: Dict[str, Package] = dict()
        for build_target in data:
            if 'steam' in build_target:
                if 'package' in build_target['steam']:
                    package_name = build_target['steam']['package']
                    if package_name not in packages:
                        package = Package(name=package_name, store=Store.STEAM, complete=False)
                        packages[package_name] = package

                    if build_target['id'] not in packages[package_name].build_targets:
                        build_target_obj = BuildTarget(name=build_target['id'], complete=False)
                        for parameter, value in build_target['steam'].items():
                            if parameter != 'package':
                                build_target_obj.parameters[parameter] = value
                        packages[package_name].build_targets[build_target['id']] = build_target_obj

            if 'butler' in build_target:
                if 'package' in build_target['butler']:
                    package_name = build_target['butler']['package']
                    if package_name not in packages:
                        package = Package(name=package_name, store=Store.BUTLER, complete=False)
                        packages[package_name] = package

                    if build_target['id'] not in packages[package_name].build_targets:
                        build_target_obj = BuildTarget(name=build_target['id'], complete=False)
                        for parameter, value in build_target['steam'].items():
                            if parameter != 'package':
                                build_target_obj.parameters[parameter] = value
                        packages[package_name].build_targets[build_target['id']] = build_target_obj


    except ClientError as e:
        print(e.response['Error']['Message'])
    else:
        return packages


# endregion

# region HELPER LIBRARY
def log(message, end="\r\n", nodate=False, logtype=LOG_INFO):
    global DEBUG_FILE

    strprint = ""
    strfile = ""
    strdate = datetime.now().strftime("%Y/%m/%d %H:%M:%S")

    if not nodate:
        strprint = strdate + " - "
        strfile = strdate + " - "

    if logtype == LOG_ERROR:
        strprint = strprint + f"{Fore.RED}"
        strprint = strprint + "ERROR: "
        strfile = strfile + "<font color='red'>"
        strfile = strfile + "ERROR: "
    elif logtype == LOG_WARNING:
        strprint = strprint + f"{Fore.YELLOW}"
        strprint = strprint + "WARNING: "
        strfile = strfile + "<font color='yellow'>"
        strfile = strfile + "WARNING: "
    elif logtype == LOG_SUCCESS:
        strprint = strprint + f"{Fore.GREEN}"
        strfile = strfile + "<font color='green'>"

    strprint = strprint + message
    strfile = strfile + message

    if logtype == LOG_ERROR or logtype == LOG_WARNING or logtype == LOG_SUCCESS:
        strprint = strprint + f"{Style.RESET_ALL}"
        strfile = strfile + "</font>"

    if end == "":
        print(strprint, end="")
    else:
        print(strprint)
    if not DEBUG_FILE.closed:
        if end == "":
            DEBUG_FILE.write(strfile)
            DEBUG_FILE.flush()
        else:
            DEBUG_FILE.write(strfile + '</br>' + end)
            DEBUG_FILE.flush()


def print_help():
    print(
        f"UCB-steam.py --platform=(standalonelinux64, standaloneosxuniversal, standalonewindows64) [--branch=(prod, beta, develop)] [--nolive] [--force] [--version=<version>] [--install] [--nodownload] [--noupload] [--noclean] [--noshutdown] [--noemail] [--steamuser=<steamuser>] [--steampassword=<steampassword>]")


# endregion

def main(argv):
    global DEBUG_FILE_NAME

    global CFG

    log("Settings environment variables...", end="")
    log("OK", logtype=LOG_SUCCESS, nodate=True)

    steam_appbranch = ""
    steam_appversion = ""

    platform = ""
    nodownload = False
    noupload = False
    noclean = False
    force = False
    install = False
    nolive = False
    simulate = False
    try:
        options, arguments = getopt.getopt(argv, "hldocsfip:b:lv:t:u:a:",
                                           ["help", "nolive", "nodownload", "noupload", "noclean", "noshutdown",
                                            "noemail",
                                            "force", "install", "simulate", "platform=", "branch=", "version=",
                                            "steamuser=",
                                            "steampassword="])
    except getopt.GetoptError:
        return 10

    for option, argument in opts:
        if option in ("-h", "--help"):
            print_help()
            return 10
        elif option in ("-p", "--platform"):
            if argument != "standalonelinux64" and argument != "standaloneosxuniversal" and argument != "standalonewindows64":
                print_help()
                return 10
            platform = argument
        elif option in ("-b", "--branch"):
            if argument != "prod" and argument != "develop" and argument != "beta" and argument != "demo":
                print_help()
                return 10
            steam_appbranch = argument
        elif option in ("-i", "--install"):
            nodownload = True
            noupload = True
            noclean = True
            install = True
        elif option in ("-d", "--nodownload"):
            nodownload = True
        elif option in ("-d", "--noupload"):
            noupload = True
        elif option in ("-d", "--noclean"):
            noclean = True
        elif option in ("-f", "--force"):
            force = True
        elif option in ("-f", "--simulate"):
            simulate = True
        elif option in ("-l", "--live"):
            nolive = True
        elif option in ("-v", "--version"):
            steam_appversion = argument
        elif option in ("-u", "--steamuser"):
            CFG['steam']['user'] = argument
        elif option in ("-a", "--steampassword"):
            CFG['steam']['password'] = argument

    buildpath = CFG['basepath'] + '/Steam/build'
    packageuploadsuccess = dict()
    CFG_ = dict()

    # region INSTALL
    # install all the dependencies and test them
    if install:
        log("Updating apt sources...", end="")
        ok = os.system("sudo apt-get update -qq -y > /dev/null 1")
        if ok > 0:
            log("Dependencies installation failed", logtype=LOG_ERROR, nodate=True)
            return 210
        log("OK", logtype=LOG_SUCCESS, nodate=True)

        log("Installing dependencies...", end="")
        ok = os.system("sudo apt-get install -qq -y mc python3-pip git lib32gcc1 python3-requests > /dev/null")
        if ok > 0:
            log("Dependencies installation failed", logtype=LOG_ERROR, nodate=True)
            return 211
        log("OK", logtype=LOG_SUCCESS, nodate=True)

        log("Installing AWS cli...", end="")
        ok = os.system('curl "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o "' + CFG[
            'basepath'] + '/awscliv2.zip" --silent')
        if ok > 0:
            log("Dependencies installation failed", logtype=LOG_ERROR, nodate=True)
            return 212
        ok = os.system('unzip -oq ' + CFG['basepath'] + '/awscliv2.zip -d ' + CFG['basepath'])
        if ok > 0:
            log("Dependencies installation failed", logtype=LOG_ERROR, nodate=True)
            return 213
        ok = os.system('rm ' + CFG['basepath'] + '/awscliv2.zip')
        if ok > 0:
            log("Dependencies installation failed", logtype=LOG_ERROR, nodate=True)
            return 214
        ok = os.system('sudo ' + CFG['basepath'] + '/aws/install --update')
        if ok > 0:
            log("Dependencies installation failed", logtype=LOG_ERROR, nodate=True)
            return 215
        log("OK", logtype=LOG_SUCCESS, nodate=True)

        log("Installing python boto3...", end="")
        ok = os.system("sudo pip3 install boto3 vdf > /dev/null")
        if ok > 0:
            log("Dependencies installation failed", logtype=LOG_ERROR, nodate=True)
            return 216
        log("OK", logtype=LOG_SUCCESS, nodate=True)

        log("Installing python vdf...", end="")
        ok = os.system("sudo pip3 install vdf > /dev/null")
        if ok > 0:
            log("Dependencies installation failed", logtype=LOG_ERROR, nodate=True)
            return 216
        log("OK", logtype=LOG_SUCCESS, nodate=True)

        log("Configuring AWS credentials...", end="")
        if not os.path.exists(CFG['homepath'] + '/.aws'):
            os.mkdir(CFG['homepath'] + '/.aws')
        write_in_file(CFG['homepath'] + '/.aws/config',
                      '[default]\r\nregion=' + CFG['aws']['region'] + '\r\noutput=json\r\naws_access_key_id=' +
                      CFG['aws']['accesskey'] + '\r\naws_secret_access_key=' + CFG['aws']['secretkey'])
        log("OK", logtype=LOG_SUCCESS, nodate=True)

        log("Testing AWS connection...", end="")
        ok = os.system('echo "Success" > ' + CFG['basepath'] + '/test_successfull.txt')
        if ok != 0:
            log("Creating temp file for connection test to AWS", logtype=LOG_ERROR, nodate=True)
            return 300
        ok = s3_upload_file(CFG['basepath'] + '/test_successfull.txt', CFG['aws']['s3bucket'],
                            'UCB/steam-parameters/test_successfull.txt')
        if ok != 0:
            log("Error uploading file to AWS UCB/steam-parameters. Check the IAM permissions", logtype=LOG_ERROR,
                nodate=True)
            return 301
        ok = s3_delete_file(CFG['aws']['s3bucket'], 'UCB/steam-parameters/test_successfull.txt')
        if ok != 0:
            log("Error deleting file from AWS UCB/steam-parameters. Check the IAM permissions", logtype=LOG_ERROR,
                nodate=True)
            return 302
        ok = s3_upload_file(CFG['basepath'] + '/test_successfull.txt', CFG['aws']['s3bucket'],
                            'UCB/unity-builds/test_successfull.txt')
        if ok != 0:
            log("Error uploading file to AWS UCB/unity-builds. Check the IAM permissions", logtype=LOG_ERROR,
                nodate=True)
            return 303
        ok = s3_delete_file(CFG['aws']['s3bucket'], 'UCB/unity-builds/test_successfull.txt')
        if ok != 0:
            log("Error deleting file from AWS UCB/unity-builds. Check the IAM permissions", logtype=LOG_ERROR,
                nodate=True)
            return 302
        ok = os.system('rm ' + CFG['basepath'] + '/test_successfull.txt')
        if ok != 0:
            log("Error deleting after connecting to AWS", logtype=LOG_ERROR, nodate=True)
            return 304
        log("OK", logtype=LOG_SUCCESS, nodate=True)

        log("Installing UCB-steam startup script...", end="")
        shutil.copyfile(CFG['basepath'] + '/UCB-steam-startup-script.example',
                        CFG['basepath'] + '/UCB-steam-startup-script')
        replace_in_file(CFG['basepath'] + '/UCB-steam-startup-script', '%basepath%', CFG['basepath'])
        ok = os.system(
            'sudo mv ' + CFG['basepath'] + '/UCB-steam-startup-script /etc/init.d/UCB-steam-startup-script > /dev/null')
        if ok != 0:
            log("Error copying UCB-steam startup script file to /etc/init.d", logtype=LOG_ERROR, nodate=True)
            return 310
        ok = os.system(
            'sudo chown root:root /etc/init.d/UCB-steam-startup-script ; sudo chmod 755 /etc/init.d/UCB-steam-startup-script ; sudo systemctl daemon-reload > /dev/null')
        if ok > 0:
            log("Error setting permission to UCB-steam startup script file", logtype=LOG_ERROR, nodate=True)
            return 311
        log("OK", logtype=LOG_SUCCESS, nodate=True)

        log("Creating folder structure for Steamworks...", end="")
        if not os.path.exists(f"{CFG['basepath']}/Steam"):
            os.mkdir(f"{CFG['basepath']}/Steam")
        if not os.path.exists(f"{CFG['basepath']}/Steam/build"):
            os.mkdir(f"{CFG['basepath']}/Steam/build")
        if not os.path.exists(f"{CFG['basepath']}/Steam/output"):
            os.mkdir(f"{CFG['basepath']}/Steam/output")
        if not os.path.exists(f"{CFG['basepath']}/Steam/scripts"):
            os.mkdir(f"{CFG['basepath']}/Steam/scripts")
        if not os.path.exists(f"{CFG['basepath']}/Steam/steamcmd"):
            os.mkdir(f"{CFG['basepath']}/Steam/steamcmd")
        if not os.path.exists(f"{CFG['basepath']}/Steam/steam-sdk"):
            os.mkdir(f"{CFG['basepath']}/Steam/steam-sdk")
        log("OK", logtype=LOG_SUCCESS, nodate=True)

        log("Testing UCB connection...", end="")
        UCB_builds = get_last_builds(steam_appbranch, platform)
        if UCB_builds is None:
            log("Error connecting to UCB", logtype=LOG_ERROR, nodate=True)
            return 21
        log("OK", logtype=LOG_SUCCESS, nodate=True)

        log("Downloading Steamworks SDK...", end="")
        if not os.path.exists(f"{CFG['basepath']}/Steam/steamcmd/linux32/steamcmd"):
            ok = s3_download_directory("UCB/steam-sdk", CFG['aws']['s3bucket'], f"{CFG['basepath']}/steam-sdk")
            if ok != 0:
                log("Error getting files from S3", logtype=LOG_ERROR, nodate=True)
                return 22

            shutil.copytree(f"{CFG['basepath']}/steam-sdk/builder_linux", f"{CFG['basepath']}/Steam/steamcmd",
                            dirs_exist_ok=True)
            st = os.stat(f"{CFG['basepath']}/Steam/steamcmd/steamcmd.sh")
            os.chmod(f"{CFG['basepath']}/Steam/steamcmd/steamcmd.sh", st.st_mode | stat.S_IEXEC)
            st = os.stat(f"{CFG['basepath']}/Steam/steamcmd/linux32/steamcmd")
            os.chmod(f"{CFG['basepath']}/Steam/steamcmd/linux32/steamcmd", st.st_mode | stat.S_IEXEC)
            shutil.rmtree(f"{CFG['basepath']}/steam-sdk")
            log("OK", logtype=LOG_SUCCESS, nodate=True)
        else:
            log("OK (dependencie already met)", logtype=LOG_SUCCESS)

        log("Testing Steam connection...", end="")
        ok = os.system(
            CFG['basepath'] + '/Steam/steamcmd/steamcmd.sh +login "' + CFG['steam']['user'] + '" "' + CFG['steam'][
                'password'] + '" +quit')
        if ok != 0:
            log("Error connecting to Steam", logtype=LOG_ERROR, nodate=True)
            return 23
        log("OK", logtype=LOG_SUCCESS, nodate=True)

        log("Creating folder structure for Butler...", end="")
        if not os.path.exists(CFG['homepath'] + '/.config'):
            os.mkdir(CFG['homepath'] + '/.config')
        if not os.path.exists(CFG['homepath'] + '/.config/itch'):
            os.mkdir(CFG['homepath'] + '/.config/itch')
        log("OK", logtype=LOG_SUCCESS, nodate=True)

        log("Setting up Butler...", end="")
        write_in_file(CFG['homepath'] + '/.config/itch/butler_creds', CFG['butler']['apikey'])
        if not os.path.exists(CFG['basepath'] + '/Butler'):
            os.mkdir(CFG['basepath'] + '/Butler')
        log("OK", logtype=LOG_SUCCESS, nodate=True)

        log("Testing Butler connection...", end="")
        ok = os.system(
            CFG['basepath'] + '/Butler/butler status ' + CFG['butler']['org'] + '/' + CFG['butler']['project'])
        if ok != 0:
            log("Error connecting to Butler", logtype=LOG_ERROR)
            return 23
        log("OK", logtype=LOG_SUCCESS, nodate=True)

        log("Testing email notification...", end="")
        str_log = '<b>Result of the UCB-steam script installation:</b>\r\n</br>\r\n</br>'
        str_log = str_log + read_from_file(DEBUG_FILE_NAME)
        str_log = str_log + '\r\n</br>\r\n</br><font color="GREEN">Everything is set up correctly. Congratulations !</font>'
        ok = send_email(CFG['email']['from'], CFG['email']['recipients'], "Steam build notification test", str_log)
        if ok != 0:
            log("Error sending email", logtype=LOG_ERROR, nodate=True)
            return 35
        log("OK", logtype=LOG_SUCCESS, nodate=True)

        log("Everything is set up correctly. Congratulations !", logtype=LOG_SUCCESS)

        return 0
    # endregion

    # region UCB builds information query
    # Get all the successful builds from Unity Cloud Build
    build_filter = ""
    if platform != "":
        build_filter = f"(Filtering on platform:{platform})"
    if build_filter != "":
        log(f"Retrieving all the builds information {build_filter}...", end="")
    else:
        log(f"Retrieving all the builds information...", end="")
    UCB_all_builds: List[Build] = get_all_builds("", platform)
    if len(UCB_all_builds) == 0:
        log("No build available in UCB", logtype=LOG_SUCCESS, nodate=True)
        if force:
            log(f"Process forced to continue (--force flag used)", logtype=LOG_WARNING, nodate=True)
        else:
            return 3

    # filter on successful builds only
    UCB_builds: Dict[str, list] = dict()
    UCB_builds['success']: List[Build] = list()
    UCB_builds['building']: List[Build] = list()
    UCB_builds['failure']: List[Build] = list()
    UCB_builds['canceled']: List[Build] = list()
    UCB_builds['unknown']: List[Build] = list()

    for build in UCB_all_builds:
        if build.status == UCBBuildStatus.SUCCESS:
            UCB_builds['success'].append(build)
        elif build.status == UCBBuildStatus.QUEUED or build.status == UCBBuildStatus.SENTTOBUILDER or build.status == UCBBuildStatus.STARTED or build.status == UCBBuildStatus.RESTARTED:
            UCB_builds['building'].append(build)
        elif build.status == UCBBuildStatus.FAILURE:
            UCB_builds['failure'].append(build)
        elif build.status == UCBBuildStatus.CANCELED:
            UCB_builds['canceled'].append(build)
        else:
            UCB_builds['unknown'].append(build)

    log("OK", logtype=LOG_SUCCESS, nodate=True)
    log(f" {len(UCB_builds['success'])} builds are waiting for processing")
    if len(UCB_builds['building']) > 0:
        log(f" {len(UCB_builds['building'])} builds are building")
    if len(UCB_builds['failure']) > 0:
        log(f" {len(UCB_builds['failure'])} builds are failed")
    if len(UCB_builds['canceled']) > 0:
        log(f" {len(UCB_builds['canceled'])} builds are canceled")
    if len(UCB_builds['unknown']) > 0:
        log(f" {len(UCB_builds['unknown'])} builds are in a unknown state")
    # endregion

    CFG_packages = get_packages()

    UCB_all_builds: List[Build] = list()
    build0 = Build('0', 'ee', 'prod-linux-64bit', UCBBuildStatus.SUCCESS, "", "", "")
    UCB_all_builds.append(build0)
    build2 = Build('0', 'ee', 'prod-macos', UCBBuildStatus.SUCCESS, "", "", "")
    UCB_all_builds.append(build2)
    build3 = Build('0', 'ee', 'prod-windows-64bit', UCBBuildStatus.SUCCESS, "", "", "")
    UCB_all_builds.append(build3)

    # region PACKAGE COMPLETION CHECK
    # identify completed builds
    for build in UCB_all_builds:
        for package_name, package in CFG_packages.items():
            if build.build_target_id in package.build_targets:
                if build.status == UCBBuildStatus.SUCCESS:
                    package.build_targets[build.build_target_id].complete = True

                package.build_targets[build.build_target_id].build = build

    # identify the full completion of a package (based on the configuration)
    for package_name, package in CFG_packages.items():
        # we assume the package is completely built
        package.complete = True

        for build_target_id, build_target in package.build_targets.items():
            # if one of the required build of the package is not complete, then the full package is incomplete
            if not build_target.complete:
                package.complete = False
    # endregion

    can_continue = False
    for package_name, package in CFG_packages.items():
        if package.complete:
            can_continue = True

    log(" One or more packages complete...", end="")
    if can_continue:
        log("OK", nodate=True, logtype=LOG_SUCCESS)
    elif force:
        log(f"Process forced to continue (--force flag used)", nodate=True, logtype=LOG_WARNING)
    else:
        log("At least one package must be complete to proceed to the next step", nodate=True, logtype=LOG_ERROR)
        return 4

    # download the builds from UCB
    if not nodownload:
        log("--------------------------------------------------------------------------", nodate=True)
        log("Downloading build from UCB...")
        for package, package_value in CFG_packages.items():
            for build in package_value['builds']:
                # filter on the platform we want (if platform is empty, it means that we must do it for all
                if build['platform'] == platform or platform == "":
                    # store the data necessary for the next steps
                    build_target_id = build['buildtargetid']
                    build_os_path = buildpath + '/' + build_target_id

                    if build_target_id == "":
                        log(" Missing field", logtype=LOG_ERROR)
                        return 5

                    if not simulate:
                        if os.path.exists(f"{build_os_path}/{build_target_id}_build.txt"):
                            os.remove(f"{build_os_path}/{build_target_id}_build.txt")

                    log(f" Preparing {build_target_id}")
                    if "build" not in build:
                        log(" Missing builds field", logtype=LOG_ERROR, nodate=True)
                        return 6
                    downloadlink = build['links']['download_primary']['href']
                    buildid = build['build']

                    if build['finished'] == "":
                        log(" The build seems to be a failed one", logtype=LOG_ERROR, nodate=True)
                        return 7
                    finisheddate = datetime.strptime(build['finished'], "%Y-%m-%dT%H:%M:%S.%fZ")
                    currentdate = datetime.now()
                    timediff = currentdate - finisheddate
                    timediffinminute = int(timediff.total_seconds() / 60)
                    log(f"  Continuing with build #{buildid} for {build_target_id} finished {timediffinminute} minutes ago...",
                        end="")
                    if timediffinminute > CFG['unity']['build_max_age']:
                        if force:
                            log(f" Process forced to continue (--force flag used)", logtype=LOG_WARNING, nodate=True)
                        else:
                            log(' The build is too old (max ' + str(CFG['unity']['build_max_age']) + 'min)',
                                logtype=LOG_ERROR,
                                nodate=True)
                            return 8
                    else:
                        log(f"OK", logtype=LOG_SUCCESS, nodate=True)

                    # store the buildtargetid in a txt file for the late cleaning process
                    if not simulate:
                        if os.path.exists(f"{buildpath}/{build_target_id}_build.txt"):
                            os.remove(f"{buildpath}/{build_target_id}_build.txt")
                        write_in_file(f"{buildpath}/{build_target_id}_build.txt", f"{build_target_id}::{buildid}")

                    zipfile = CFG['basepath'] + '/ucb' + build_target_id + '.zip'

                    log(f"  Deleting old files in {build_os_path}...", end="")
                    if not simulate:
                        if os.path.exists(zipfile):
                            os.remove(zipfile)
                        if os.path.exists(build_os_path):
                            shutil.rmtree(build_os_path, ignore_errors=True)
                    log("OK", logtype=LOG_SUCCESS, nodate=True)

                    log('  Downloading the built zip file ' + zipfile + '...', end="")
                    if not simulate:
                        urllib.request.urlretrieve(downloadlink, zipfile)
                    log("OK", logtype=LOG_SUCCESS, nodate=True)

                    log('  Extracting the zip file in ' + build_os_path + '...', end="")
                    if not simulate:
                        with ZipFile(zipfile, "r") as zipObj:
                            zipObj.extractall(build_os_path)
                            log("OK", logtype=LOG_SUCCESS, nodate=True)
                    else:
                        log("OK", logtype=LOG_SUCCESS, nodate=True)

                    s3path = 'UCB/unity-builds/' + steam_appbranch + '/ucb' + build_target_id + '.zip'
                    log('  Uploading copy to S3 ' + s3path + ' ...', end="")
                    if not simulate:
                        ok = s3_upload_file(zipfile, CFG['aws']['s3bucket'], s3path)
                    else:
                        ok = 0

                    if ok != 0:
                        log('Error uploading file "ucb' + build_target_id + '.zip" to AWS ' + s3path + '. Check the IAM permissions',
                            logtype=LOG_ERROR, nodate=True)
                        return 9
                    log("OK", logtype=LOG_SUCCESS, nodate=True)

    log("--------------------------------------------------------------------------", nodate=True)
    log("Get version from source file...")
    for package_name, package in CFG_packages.items():
        for build_target_id, build_target in package.build_targets:
            build_os_path = buildpath + '/' + build_target_id

            if steam_appversion == "":
                log('  Get the version of the build from files...', end="")
                pathFileVersion = glob.glob(build_os_path + "/**/UCB_version.txt", recursive=True)

                if len(pathFileVersion) == 1:
                    if os.path.exists(pathFileVersion[0]):
                        steam_appversion = read_from_file(pathFileVersion[0])
                        steam_appversion = steam_appversion.rstrip('\n')
                        if not simulate:
                            os.remove(pathFileVersion[0])

                    if steam_appversion != "":
                        log(" " + steam_appversion + " ", logtype=LOG_INFO, nodate=True, end="")
                        log("OK ", logtype=LOG_SUCCESS, nodate=True)
                else:
                    log(f"File version UCB_version.txt was not found in build directory {build_os_path}",
                        logtype=LOG_WARNING, nodate=True)

    if not noupload:
        log("--------------------------------------------------------------------------", nodate=True)
        log("Uploading files to stores...")

        # region STEAM
        # create the structure used to identify the upload success for a complete package
        for package_name, package in CFG_packages.items():
            if package.store == Store.STEAM:
                package.uploaded = False

        for package_name, package in CFG_packages.items():
            first = True
            # we only want to build the packages that are complete
            if package.store == Store.STEAM and package.complete:
                log(f'Starting Steam process for package {package_name}...')
                app_id = ""

                for build_target_id, build_target in package.build_targets.items():
                    # TODO
                    # filter on the platform we want (if platform is empty, it means that we must do it for all
                    # if build['platform'] == platform or platform == "":
                    # store the data necessary for the next steps

                    # find the data related to the branch we want to build
                    depot_id = build_target.parameters['depot_id']
                    branch_name = build_target.parameters['branch_name']
                    live = build_target.parameters['live']

                    # now prepare the steam files
                    # first time we loop: prepare the main steam file
                    if first:
                        first = False

                        app_id = build_target.parameters['app_id']
                        log(f' Preparing main Steam file for app {app_id}...', end="")
                        if not simulate:
                            shutil.copyfile(f"{CFG['basepath']}/Steam/scripts/template_app_build.vdf",
                                            f"{CFG['basepath']}/Steam/scripts/app_build_{app_id}.vdf")

                            replace_in_file(f"{CFG['basepath']}/Steam/scripts/app_build_{app_id}.vdf",
                                            "%basepath%", CFG['basepath'])
                            replace_in_file(f"{CFG['basepath']}/Steam/scripts/app_build_{app_id}.vdf",
                                            "%version%", steam_appversion)
                            replace_in_file(f"{CFG['basepath']}/Steam/scripts/app_build_{app_id}.vdf",
                                            "%branch_name%", branch_name)
                            replace_in_file(f"{CFG['basepath']}/Steam/scripts/app_build_{app_id}.vdf",
                                            "%app_id%", app_id)

                            if not nolive:
                                replace_in_file(f"{CFG['basepath']}/Steam/scripts/app_build_{app_id}.vdf",
                                                "%live%", live)
                            else:
                                replace_in_file(f"{CFG['basepath']}/Steam/scripts/app_build_{app_id}.vdf",
                                                "%live%", "")
                        log("OK", logtype=LOG_SUCCESS, nodate=True)

                        # then the depot files
                    log(f' Preparing platform Steam file for depot {depot_id} / {build_target_id}...',
                        end="")
                    if not simulate:
                        shutil.copyfile(
                            f"{CFG['basepath']}/Steam/scripts/template_depot_build_buildtarget.vdf",
                            f"{CFG['basepath']}/Steam/scripts/depot_build_{build_target_id}.vdf")

                        replace_in_file(
                            f"{CFG['basepath']}/Steam/scripts/depot_build_{build_target_id}.vdf",
                            "%depot_id%", depot_id)
                        replace_in_file(
                            f"{CFG['basepath']}/Steam/scripts/depot_build_{build_target_id}.vdf",
                            "%buildtargetid%", build_target_id)
                        replace_in_file(
                            f"{CFG['basepath']}/Steam/scripts/depot_build_{build_target_id}.vdf",
                            "%basepath%", CFG['basepath'])

                        data = vdf.load(open(f"{CFG['basepath']}/Steam/scripts/app_build_{app_id}.vdf"))
                        data['appbuild']['depots'][depot_id] = f"depot_build_{build_target_id}.vdf"

                        indented_vdf = vdf.dumps(data, pretty=True)

                        write_in_file(f"{CFG['basepath']}/Steam/scripts/app_build_{app_id}.vdf",
                                      indented_vdf)

                    log("OK", logtype=LOG_SUCCESS, nodate=True)

                log(" Building Steam packages...", end="")
                if app_id != "":
                    cmd = f'{CFG["basepath"]}/Steam/steamcmd/steamcmd.sh +login "{CFG["steam"]["user"]}" "{CFG["steam"]["password"]}" +run_app_build {CFG["basepath"]}/Steam/scripts/app_build_{app_id}.vdf +quit'
                    if not simulate:
                        ok = os.system(cmd)
                    else:
                        ok = 0

                    if ok != 0:
                        log(f" Executing the bash file {CFG['basepath']}/Steam/steamcmd/steamcmd.sh (exitcode={ok})",
                            logtype=LOG_ERROR, nodate=True)
                        return 9

                    package.uploaded = True

                    log("OK", logtype=LOG_SUCCESS, nodate=True)

                    if simulate:
                        log("  " + cmd)
                else:
                    log("app_id is empty", logtype=LOG_ERROR, nodate=True)
                    return 9
            else:
                log(f' Package {package_name} is not complete and will not be processed for Steam...', logtype=LOG_WARNING)
        # endregion

        # region BUTLER
        # create the structure used to identify the upload success for a package
        for package_name, package in CFG_packages.items():
            if package.store == Store.ITCH:
                package.uploaded = False

        for package_name, package in CFG_packages.items():
            # we only want to build the packages that are complete
            if package.store == Store.ITCH and package.complete:
                log(f'Starting Butler process for package {package_name}...')

                for build_target_id, build_target in package.build_targets.items():
                    # TODO
                    # filter on the platform we want (if platform is empty, it means that we must do it for all
                    # if build['platform'] == platform or platform == "":
                    # store the data necessary for the next steps

                    found = False
                    # find the data related to the branch we want to build
                    butler_channel = build_target.parameters['channel']
                    build_path = f"{CFG['basepath']}/Steam/build/{build_target_id}"

                    log(f" Building itch.io(Butler) {build_target_id} packages...", end="")
                    cmd = f"{CFG['basepath']}/Butler/butler push {build_path} {CFG['butler']['org']}/{CFG['butler']['project']}:{butler_channel} --userversion={steam_appversion} --if-changed"
                    if not simulate:
                        ok = os.system(cmd)
                    else:
                        ok = 0

                    if ok != 0:
                        log(f"Executing Butler {CFG['basepath']}/Butler/butler (exitcode={ok})",
                            logtype=LOG_ERROR)
                        return 10

                    found = True

                    package.uploaded = True

                    log("OK", logtype=LOG_SUCCESS, nodate=True)

                    if simulate:
                        log("  " + cmd)

                    if not found:
                        log(f"There is no Butler configuration for the target {build_target_id}", logtype=LOG_WARNING)
            else:
                log(f' Package {package_name} is not complete and will not be processed for Butler...', logtype=LOG_WARNING)
        # endregion

    if not noclean:
        log("--------------------------------------------------------------------------", nodate=True)
        log("Cleaning successfully upload build in UCB...")
        # let's remove the build successfully uploaded to Steam or Butler from UCB
        # clean only the packages that are successful
        for package, package_value in packageuploadsuccess.items():
            complete = True
            for build_target, buildtargetvalue in package_value.items():
                for uploadprocess, uploadprocessvalue in buildtargetvalue.items():
                    if not uploadprocessvalue:
                        complete = False

            if complete:
                log(f" Cleaning package {package}...")
                # cleanup everything related to this package

                for build in UCB_builds['success'] + UCB_builds['building'] + UCB_builds['failure'] + UCB_builds[
                    'canceled']:
                    for build_target in package_value.keys():
                        if build.build_target_id == build_target:
                            log(f"  Deleting build #{build.number} for buildtarget {build_target} (status: {build.status})...",
                                end="")
                            if not simulate:
                                delete_build(build_target, build.number)
                            log("OK", logtype=LOG_SUCCESS, nodate=True)

    log("--------------------------------------------------------------------------", nodate=True)
    log("All done!")
    return 0


if __name__ == "__main__":
    # load the configuration from the config file
    currentpath = os.path.dirname(os.path.abspath(__file__))
    with open(currentpath + '/UCB-steam.config', "r") as ymlfile:
        CFG = yaml.load(ymlfile, Loader=yaml.FullLoader)

    if CFG is None:
        codeok = 11
        exit()

    # create the log directory if it does not exists
    if not os.path.exists(f"{CFG['logpath']}"):
        os.mkdir(f"{CFG['logpath']}")
    # set the log file name with the current datetime
    DEBUG_FILE_NAME = CFG['logpath'] + '/' + datetime.now().strftime("%Y%m%d_%H%M%S") + '.html'
    # open the logfile for writing
    DEBUG_FILE = open(DEBUG_FILE_NAME, "wt")

    codeok = 0
    noshutdown = False
    noemail = False
    try:
        opts, args = getopt.getopt(sys.argv[1:], "hldocsfip:b:lv:t:u:a:",
                                   ["help", "nolive", "nodownload", "noupload", "noclean", "noshutdown", "noemail",
                                    "force", "install", "simulate", "platform=", "branch=", "version=",
                                    "steamuser=",
                                    "steampassword="])
        for opt, arg in opts:
            if opt in ("-s", "--noshutdown"):
                noshutdown = True
            elif opt in ("-i", "--noemail"):
                noemail = True
            elif opt in ("-i", "--install"):
                noshutdown = True
    except getopt.GetoptError:
        print_help()
        codeok = 11

    if codeok != 10 and codeok != 11:
        codeok = main(sys.argv[1:])
        if not noshutdown and codeok != 10:
            log("Shutting down computer...")
            os.system("sudo shutdown +3")

    log("--- Script execution time : %s seconds ---" % (time.time() - start_time))
    # close the logfile
    DEBUG_FILE.close()
    if codeok != 10 and codeok != 11 and not noemail:
        send_email(CFG['email']['from'], CFG['email']['recipients'], "Steam build result",
                   read_from_file(DEBUG_FILE_NAME))
