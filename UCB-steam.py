__version__ = "0.3"

import json
import logging
import re
import urllib.request
from zipfile import ZipFile
import os
import stat
import sys, getopt
import shutil
from colorama import Fore, Back, Style
import copy
import yaml
import site
import glob
import vdf

import requests
from datetime import datetime
import time
import boto3
from botocore.exceptions import ClientError

import time

start_time = time.time()

LOG_ERROR = 0
LOG_WARNING = 1
LOG_INFO = 2
LOG_SUCCESS = 3

global DEBUG_FILE
global DEBUG_FILE_NAME

global CFG


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


def get_last_builds(branch="", platform=""):
    url = '{}/buildtargets?include_last_success=true'.format(api_url())
    response = requests.get(url, headers=headers())

    datatemp = []

    if not response.ok:
        log(f"Getting build template failed: {response.text}", type=LOG_ERROR)
        return datatemp

    data = response.json()
    datatemp = copy.deepcopy(data)
    # let's filter the result on the requested branch only
    for i in reversed(range(0, len(data))):
        build = data[i]

        # identify if the build is successfull
        if not "builds" in build:
            # log(f"Missing builds field for {build["buildtargetid"]}", type=LOG_ERROR)
            datatemp.pop(i)
            continue

        # filter on branch
        if branch != "":
            if not build['buildtargetid'] == None:
                # the branch name is at the beginning of the build target name (ex: beta-windows-64bit)
                tabtemp = build['buildtargetid'].split("-")
                if (len(tabtemp) > 0):
                    if (tabtemp[0] != branch):
                        # the branch name is different: remove the build from the result
                        datatemp.pop(i)
                        continue
                else:
                    log(f"The name of the branch was not detected in {build['buildtargetid']}", type=LOG_ERROR)
                    datatemp.pop(i)
                    continue
            else:
                log(f"The buildtargetid was not detected", type=LOG_ERROR)
                datatemp.pop(i)
                continue

        # filter on platform
        if platform != "":
            if not build['platform'] == None:
                if (build['platform'] != platform):
                    # the branch name is different: remove the build from the result
                    datatemp.pop(i)
                    continue
            else:
                log(f"The platform was not detected", type=LOG_ERROR)
                datatemp.pop(i)
                continue

    return datatemp


def get_all_builds(buildtarget="", platform=""):
    url = '{}/buildtargets/_all/builds'.format(api_url())
    response = requests.get(url, headers=headers())

    datatemp = []

    if not response.ok:
        log(f"Getting build template failed: {response.text}", type=LOG_ERROR)
        return datatemp

    data = response.json()
    datatemp = copy.deepcopy(data)
    # let's filter the result on the requested branch only
    for i in reversed(range(0, len(data))):
        build = data[i]

        # identify if the build is successfull
        if not "build" in build:
            # log(f"Missing build field for {build["build"]}", type=LOG_ERROR)
            datatemp.pop(i)
            continue

        # filter on branch
        if buildtarget != "":
            if build['buildtargetid'] == None:
                if build['buildtargetid'] != buildtarget:
                    datatemp.pop(i)
                    continue
            else:
                log(f"The buildtargetid was not detected", type=LOG_ERROR)
                datatemp.pop(i)
                continue

        # filter on platform
        if platform != "":
            if not build['platform'] == None:
                if (build['platform'] != platform):
                    # the branch name is different: remove the build from the result
                    datatemp.pop(i)
                    continue
            else:
                log(f"The platform was not detected", type=LOG_ERROR)
                datatemp.pop(i)
                continue

    return datatemp


def delete_build(buildtargetid, build):
    deleted = True
    url = '{}/artifacts/delete'.format(api_url())

    data = {'builds': [{"buildtargetid": buildtargetid, "build": int(build)}]}

    response = requests.post(url, headers=headers(), json=data)

    if not response.ok:
        deleted = False
        log(f"Deleting build target failed: {response.text}", type=LOG_ERROR)

    return deleted


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
        log(e.response['Error']['Message'], type=LOG_ERROR)
        return 461
    else:
        log("Email sent! Message ID:"),
        log(response['MessageId'])
        return 0


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
        log(e.response['Error']['Message'], type=LOG_ERROR)
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
        log(e.response['Error']['Message'], type=LOG_ERROR)
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
        log(e.response['Error']['Message'], type=LOG_ERROR)
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
        log(e.response['Error']['Message'], type=LOG_ERROR)
        return 460


def log(message, end="\r\n", nodate=False, type=LOG_INFO):
    global DEBUG_FILE

    strprint = ""
    strfile = ""
    strdate = datetime.now().strftime("%Y/%m/%d %H:%M:%S")

    if nodate == False:
        strprint = strdate + " - "
        strfile = strdate + " - "

    if type == LOG_ERROR:
        strprint = strprint + f"{Fore.RED}"
        strprint = strprint + "ERROR: "
        strfile = strfile + "<font color='red'>"
        strfile = strfile + "ERROR: "
    elif type == LOG_WARNING:
        strprint = strprint + f"{Fore.YELLOW}"
        strprint = strprint + "WARNING: "
        strfile = strfile + "<font color='yellow'>"
        strfile = strfile + "WARNING: "
    elif type == LOG_SUCCESS:
        strprint = strprint + f"{Fore.GREEN}"
        strfile = strfile + "<font color='green'>"

    strprint = strprint + message
    strfile = strfile + message

    if type == LOG_ERROR or type == LOG_WARNING or type == LOG_SUCCESS:
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
        f"UCB-steam.py --platform=(standalonelinux64, standaloneosxuniversal, standalonewindows64) [--branch=(prod, beta, develop)] [--nolive] [--force] [--version=<version>] [--install] [--nodownload] [--noupload] [--noclean] [--noshutdown]  [--noemail][--steamappid=<steamappid>] [--steamuser=<steamuser>] [--steampassword=<steampassword>]")


def main(argv):
    global DEBUG_FILE_NAME

    global CFG

    log("Settings environment variables...", end="")
    log("OK", type=LOG_SUCCESS, nodate=True)

    steam_appbranch = ""
    steam_appversion = ""
    steam_appid = ""

    platform = ""
    nodownload = False
    noupload = False
    noclean = False
    noshutdown = False
    noemail = False
    force = False
    install = False
    nolive = False
    simulate = False
    try:
        opts, args = getopt.getopt(argv, "hldocsfip:b:lv:t:u:a:",
                                   ["help", "nolive", "nodownload", "noupload", "noclean", "noshutdown", "noemail",
                                    "force", "install", "simulate", "platform=", "branch=", "version=", "steamappid=", "steamuser=",
                                    "steampassword="])
    except getopt.GetoptError:
        return 10

    for opt, arg in opts:
        if opt in ("-h", "--help"):
            print_help()
            return 10
        elif opt in ("-p", "--platform"):
            if arg != "standalonelinux64" and arg != "standaloneosxuniversal" and arg != "standalonewindows64":
                print_help()
                return 10
            platform = arg
        elif opt in ("-b", "--branch"):
            if arg != "prod" and arg != "develop" and arg != "beta" and arg != "demo":
                print_help()
                return 10
            steam_appbranch = arg
        elif opt in ("-i", "--install"):
            nodependencies = True
            nodownload = True
            noupload = True
            noclean = True
            noshutdown = True
            install = True
        elif opt in ("-d", "--nodownload"):
            nodownload = True
        elif opt in ("-d", "--noupload"):
            noupload = True
        elif opt in ("-d", "--noclean"):
            noclean = True
        elif opt in ("-s", "--noshutdown"):
            noshutdown = True
        elif opt in ("-s", "--noemail"):
            noemail = True
        elif opt in ("-f", "--force"):
            force = True
        elif opt in ("-f", "--simulate"):
            simulate = True
        elif opt in ("-l", "--live"):
            nolive = True
        elif opt in ("-v", "--version"):
            steam_appversion = arg
        elif opt in ("-u", "--steamuser"):
            CFG['steam']['user'] = arg
        elif opt in ("-a", "--steampassword"):
            CFG['steam']['password'] = arg
        elif opt in ("-t", "--steamappid"):
            steam_appid = arg

    buildpath = CFG['basepath'] + '/Steam/build'
    packageuploadsuccess = dict()
    packagecomplete = dict()

    # region INSTALL
    # install all the dependencies and test them
    if install:
        log("Updating apt sources...", end="")
        ok = os.system("sudo apt-get update -qq -y > /dev/null 1")
        if ok > 0:
            log("Dependencies installation failed", type=LOG_ERROR, nodate=True)
            return 210
        log("OK", type=LOG_SUCCESS, nodate=True)

        log("Installing dependencies...", end="")
        ok = os.system("sudo apt-get install -qq -y mc python3-pip git lib32gcc1 python3-requests > /dev/null")
        if ok > 0:
            log("Dependencies installation failed", type=LOG_ERROR, nodate=True)
            return 211
        log("OK", type=LOG_SUCCESS, nodate=True)

        log("Installing AWS cli...", end="")
        ok = os.system('curl "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o "' + CFG[
            'basepath'] + '/awscliv2.zip" --silent')
        if ok > 0:
            log("Dependencies installation failed", type=LOG_ERROR, nodate=True)
            return 212
        ok = os.system('unzip -oq ' + CFG['basepath'] + '/awscliv2.zip -d ' + CFG['basepath'])
        if ok > 0:
            log("Dependencies installation failed", type=LOG_ERROR, nodate=True)
            return 213
        ok = os.system('rm ' + CFG['basepath'] + '/awscliv2.zip')
        if ok > 0:
            log("Dependencies installation failed", type=LOG_ERROR, nodate=True)
            return 214
        ok = os.system('sudo ' + CFG['basepath'] + '/aws/install --update')
        if ok > 0:
            log("Dependencies installation failed", type=LOG_ERROR, nodate=True)
            return 215
        log("OK", type=LOG_SUCCESS, nodate=True)

        log("Installing python boto3...", end="")
        ok = os.system("sudo pip3 install boto3 vdf > /dev/null")
        if ok > 0:
            log("Dependencies installation failed", type=LOG_ERROR, nodate=True)
            return 216
        log("OK", type=LOG_SUCCESS, nodate=True)

        log("Installing python vdf...", end="")
        ok = os.system("sudo pip3 install vdf > /dev/null")
        if ok > 0:
            log("Dependencies installation failed", type=LOG_ERROR, nodate=True)
            return 216
        log("OK", type=LOG_SUCCESS, nodate=True)

        log("Configuring AWS credentials...", end="")
        if not os.path.exists(CFG['homepath'] + '/.aws'):
            os.mkdir(CFG['homepath'] + '/.aws')
        write_in_file(CFG['homepath'] + '/.aws/config',
                      '[default]\r\nregion=' + CFG['aws']['region'] + '\r\noutput=json\r\naws_access_key_id=' +
                      CFG['aws']['accesskey'] + '\r\naws_secret_access_key=' + CFG['aws']['secretkey'])
        log("OK", type=LOG_SUCCESS, nodate=True)

        log("Testing AWS connection...", end="")
        ok = os.system('echo "Success" > ' + CFG['basepath'] + '/test_successfull.txt')
        if ok != 0:
            log("Creating temp file for connection test to AWS", type=LOG_ERROR, nodate=True)
            return 300
        ok = s3_upload_file(CFG['basepath'] + '/test_successfull.txt', CFG['aws']['s3bucket'],
                            'UCB/steam-parameters/test_successfull.txt')
        if ok != 0:
            log("Error uploading file to AWS UCB/steam-parameters. Check the IAM permissions", type=LOG_ERROR,
                nodate=True)
            return 301
        ok = s3_delete_file(CFG['aws']['s3bucket'], 'UCB/steam-parameters/test_successfull.txt')
        if ok != 0:
            log("Error deleting file from AWS UCB/steam-parameters. Check the IAM permissions", type=LOG_ERROR,
                nodate=True)
            return 302
        ok = s3_upload_file(CFG['basepath'] + '/test_successfull.txt', CFG['aws']['s3bucket'],
                            'UCB/unity-builds/test_successfull.txt')
        if ok != 0:
            log("Error uploading file to AWS UCB/unity-builds. Check the IAM permissions", type=LOG_ERROR, nodate=True)
            return 303
        ok = s3_delete_file(CFG['aws']['s3bucket'], 'UCB/unity-builds/test_successfull.txt')
        if ok != 0:
            log("Error deleting file from AWS UCB/unity-builds. Check the IAM permissions", type=LOG_ERROR, nodate=True)
            return 302
        ok = os.system('rm ' + CFG['basepath'] + '/test_successfull.txt')
        if ok != 0:
            log("Error deleting after connecting to AWS", type=LOG_ERROR, nodate=True)
            return 304
        log("OK", type=LOG_SUCCESS, nodate=True)

        log("Installing UCB-steam startup script...", end="")
        shutil.copyfile(CFG['basepath'] + '/UCB-steam-startup-script.example',
                        CFG['basepath'] + '/UCB-steam-startup-script')
        replace_in_file(CFG['basepath'] + '/UCB-steam-startup-script', '%basepath%', CFG['basepath'])
        ok = os.system(
            'sudo mv ' + CFG['basepath'] + '/UCB-steam-startup-script /etc/init.d/UCB-steam-startup-script > /dev/null')
        if ok != 0:
            log("Error copying UCB-steam startup script file to /etc/init.d", type=LOG_ERROR, nodate=True)
            return 310
        ok = os.system(
            'sudo chown root:root /etc/init.d/UCB-steam-startup-script ; sudo chmod 755 /etc/init.d/UCB-steam-startup-script ; sudo systemctl daemon-reload > /dev/null')
        if ok > 0:
            log("Error setting permission to UCB-steam startup script file", type=LOG_ERROR, nodate=True)
            return 311
        log("OK", type=LOG_SUCCESS, nodate=True)

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
        log("OK", type=LOG_SUCCESS, nodate=True)

        log("Testing UCB connection...", end="")
        builds = get_last_builds(steam_appbranch, platform)
        if builds == None:
            log("Error connecting to UCB", type=LOG_ERROR, nodate=True)
            return 21
        log("OK", type=LOG_SUCCESS, nodate=True)

        log("Downloadng Steamworks SDK...", end="")
        if not os.path.exists(f"{CFG['basepath']}/Steam/steamcmd/linux32/steamcmd"):
            ok = s3_download_directory("UCB/steam-sdk", CFG['aws']['s3bucket'], f"{CFG['basepath']}/steam-sdk")
            if ok != 0:
                log("Error getting files from S3", type=LOG_ERROR, nodate=True)
                return 22

            shutil.copytree(f"{CFG['basepath']}/steam-sdk/builder_linux", f"{CFG['basepath']}/Steam/steamcmd",
                            dirs_exist_ok=True)
            st = os.stat(f"{CFG['basepath']}/Steam/steamcmd/steamcmd.sh")
            os.chmod(f"{CFG['basepath']}/Steam/steamcmd/steamcmd.sh", st.st_mode | stat.S_IEXEC)
            st = os.stat(f"{CFG['basepath']}/Steam/steamcmd/linux32/steamcmd")
            os.chmod(f"{CFG['basepath']}/Steam/steamcmd/linux32/steamcmd", st.st_mode | stat.S_IEXEC)
            shutil.rmtree(f"{CFG['basepath']}/steam-sdk")
            log("OK", type=LOG_SUCCESS, nodate=True)
        else:
            log("OK (dependencie already met)", type=LOG_SUCCESS)

        log("Testing Steam connection...", end="")
        ok = os.system(
            CFG['basepath'] + '/Steam/steamcmd/steamcmd.sh +login "' + CFG['steam']['user'] + '" "' + CFG['steam'][
                'password'] + '" +quit')
        if ok != 0:
            log("Error connecting to Steam", type=LOG_ERROR, nodate=True)
            return 23
        log("OK", type=LOG_SUCCESS, nodate=True)

        log("Creating folder structure for Butler...", end="")
        if not os.path.exists(CFG['homepath'] + '/.config'):
            ok = os.mkdir(CFG['homepath'] + '/.config')
        if not os.path.exists(CFG['homepath'] + '/.config/itch'):
            ok = os.mkdir(CFG['homepath'] + '/.config/itch')
        log("OK", type=LOG_SUCCESS, nodate=True)

        log("Setting up Butler...", end="")
        write_in_file(CFG['homepath'] + '/.config/itch/butler_creds', CFG['butler']['apikey'])
        if not os.path.exists(CFG['basepath'] + '/Butler'):
            ok = os.mkdir(CFG['basepath'] + '/Butler')
            if ok != 0:
                log('Error creating Butler directory: ' + CFG['basepath'] + '/Butler', type=LOG_ERROR, nodate=True)
                return 26
        log("OK", type=LOG_SUCCESS, nodate=True)

        log("Testing Butler connection...", end="")
        ok = os.system(
            CFG['basepath'] + '/Butler/butler status ' + CFG['butler']['org'] + '/' + CFG['butler']['project'])
        if ok != 0:
            log("Error connecting to Butler", type=LOG_ERROR)
            return 23
        log("OK", type=LOG_SUCCESS, nodate=True)

        log("Testing email notification...", end="")
        strLog = '<b>Result of the UCB-steam script installation:</b>\r\n</br>\r\n</br>'
        strLog = strLog + read_from_file(DEBUG_FILE_NAME)
        strLog = strLog + '\r\n</br>\r\n</br><font color="GREEN">Everything is set up correctly. Congratulations !</font>'
        ok = send_email(CFG['email']['from'], CFG['email']['recipients'], "Steam build notification test", strLog)
        if ok != 0:
            log("Error sending email", type=LOG_ERROR, nodate=True)
            return 35
        log("OK", type=LOG_SUCCESS, nodate=True)

        log("Everything is set up correctly. Congratulations !", type=LOG_SUCCESS)

        return 0
    # endregion

    # Get all the successful builds from Unity Cloud Build
    filter = ""
    if platform != "":
        filter = f"(Filtering on platform:{platform})"
    log(f"Retrieving all the builds information {filter}...", end="")
    allbuilds = get_all_builds("", platform)
    if len(allbuilds) == 0:
        log("Retrieving the information. No build available in UCB", type=LOG_ERROR, nodate=True)
        if force:
            log(f"Process forced to continue (--force flag used)", type=LOG_WARNING, nodate=True)
        else:
            return 3

    # filter on successful builds only
    builds = dict()
    builds['success'] = list()
    builds['building'] = list()
    builds['failure'] = list()
    builds['canceled'] = list()
    builds['unknown'] = list()

    for build in allbuilds:
        if build['buildStatus'] == 'success':
            builds['success'].append(build)
        elif build['buildStatus'] == 'queued' or build['buildStatus'] == 'sentToBuilder' or build['buildStatus'] == 'started' or build['buildStatus'] == 'restarted':
            builds['building'].append(build)
        elif build['buildStatus'] == 'failure':
            builds['failure'].append(build)
        elif build['buildStatus'] == 'canceled':
            builds['canceled'].append(build)
        else:
            builds['unknown'].append(build)

    log("OK", type=LOG_SUCCESS, nodate=True)
    log(f" {len(builds['success'])} builds are waiting for processing")
    if(len(builds['building']) > 0):
        log(f" {len(builds['building'])} builds are building")
    if (len(builds['failure']) > 0):
        log(f" {len(builds['failure'])} builds are failed")
    if (len(builds['canceled']) > 0):
        log(f" {len(builds['canceled'])} builds are canceled")
    if (len(builds['unknown']) > 0):
        log(f" {len(builds['unknown'])} builds are in a unknown state")

    # build package structure for consistency check
    # region STEAM
    steampackages = dict()
    for buildtarget in CFG['buildtargets']:
        for buildtargetid in buildtarget.keys():
            if 'steam' in buildtarget[buildtargetid]:
                if 'package' in buildtarget[buildtargetid]['steam']:
                    package = buildtarget[buildtargetid]['steam']['package']
                    if package not in steampackages:
                        steampackages[package] = dict()

                    steampackages[package][buildtargetid] = dict()
                    steampackages[package][buildtargetid]['complete'] = False

    for build in allbuilds:
        if build['platform'] == platform or platform == "":
            buildtargetid = build['buildtargetid']
            for buildtarget in CFG['buildtargets']:
                if buildtargetid in buildtarget.keys():
                    if 'steam' in buildtarget[buildtargetid]:
                        if 'package' in buildtarget[buildtargetid]['steam']:
                            package = buildtarget[buildtargetid]['steam']['package']

                            if build['buildStatus'] == 'success':
                                steampackages[package][buildtargetid]['complete'] = True

                            if 'builds' not in steampackages[package][buildtargetid]:
                                steampackages[package][buildtargetid]['builds'] = list()
                            steampackages[package][buildtargetid]['builds'].append(build)

    # identify the full completion of a package (based on the configuration)
    for package in steampackages.keys():
        if package not in packagecomplete.keys():
            packagecomplete[package] = dict()
            packagecomplete[package]['complete'] = True
            packagecomplete[package]['builds'] = list()

        packagecomplete[package]['steam'] = True

        for buildtargetid, buildtargetvalue in steampackages[package].items():
            if 'builds' in buildtargetvalue:
                for build in buildtargetvalue['builds']:
                    if build not in packagecomplete[package]['builds'] and build['buildStatus'] == 'success':
                        packagecomplete[package]['builds'].append(build)

            if buildtargetvalue['complete'] == False:
                packagecomplete[package]['steam'] = False
                packagecomplete[package]['complete'] = False
    # endregion

    # region BUTLER
    butlerpackages = dict()
    for buildtarget in CFG['buildtargets']:
        for buildtargetid in buildtarget.keys():
            if 'butler' in buildtarget[buildtargetid]:
                if 'package' in buildtarget[buildtargetid]['butler']:
                    package = buildtarget[buildtargetid]['butler']['package']
                    if package not in butlerpackages:
                        butlerpackages[package] = dict()

                    butlerpackages[package][buildtargetid] = dict()
                    butlerpackages[package][buildtargetid]['complete'] = False

    for build in allbuilds:
        if build['platform'] == platform or platform == "":
            buildtargetid = build['buildtargetid']
            for buildtarget in CFG['buildtargets']:
                if buildtargetid in buildtarget.keys():
                    if 'butler' in buildtarget[buildtargetid]:
                        if 'package' in buildtarget[buildtargetid]['butler']:
                            package = buildtarget[buildtargetid]['butler']['package']

                            if build['buildStatus'] == 'success':
                                butlerpackages[package][buildtargetid]['complete'] = True

                            if 'builds' not in butlerpackages[package][buildtargetid]:
                                butlerpackages[package][buildtargetid]['builds'] = list()
                            butlerpackages[package][buildtargetid]['builds'].append(build)

    # identify the full completion of a package (based on the configuration)
    for package in butlerpackages.keys():
        if package not in packagecomplete.keys():
            packagecomplete[package] = dict()
            packagecomplete[package]['complete'] = True
            packagecomplete[package]['builds'] = list()

        packagecomplete[package]['butler'] = True

        for buildtargetid, buildtargetvalue in butlerpackages[package].items():
            if 'builds' in buildtargetvalue:
                for build in buildtargetvalue['builds']:
                    if build not in packagecomplete[package]['builds'] and build['buildStatus'] == 'success':
                        packagecomplete[package]['builds'].append(build)

            if buildtargetvalue['complete'] == False:
                packagecomplete[package]['butler'] = False
                packagecomplete[package]['complete'] = False

    # endregion

    cancontinue = False
    for package, packagevalue in packagecomplete.items():
        if packagevalue['complete']:
            cancontinue = True

    log(" One or more packages complete...", end="")
    if cancontinue:
        log("OK", nodate=True, type=LOG_SUCCESS)
    elif force:
        log(f"Process forced to continue (--force flag used)", nodate=True, type=LOG_WARNING)
    else:
        log("At least one package must be complete to proceed to the next step", nodate=True, type=LOG_ERROR)
        return 4

    # download the builds from UCB
    if not nodownload:
        log("--------------------------------------------------------------------------", nodate=True)
        log("Downloading build from UCB...")
        for package, packagevalue in packagecomplete.items():
            for build in packagevalue['builds']:
                # filter on the platform we want (if platform is empty, it means that we must do it for all
                if build['platform'] == platform or platform == "":
                    # store the data necessary for the next steps
                    buildtargetid = build['buildtargetid']
                    buildospath = buildpath + '/' + buildtargetid

                    if buildtargetid == "":
                        log(" Missing field", type=LOG_ERROR)
                        return 5

                    if not simulate:
                        if os.path.exists(f"{buildospath}/{buildtargetid}_build.txt"):
                            os.remove(f"{buildospath}/{buildtargetid}_build.txt")

                    log(f" Preparing {buildtargetid}")
                    if not "build" in build:
                        log(" Missing builds field", type=LOG_ERROR, nodate=True)
                        return 6
                    downloadlink = build['links']['download_primary']['href']
                    buildid = build['build']

                    if build['finished'] == "":
                        log(" The build seems to be a failed one", type=LOG_ERROR, nodate=True)
                        return 7
                    finisheddate = datetime.strptime(build['finished'], "%Y-%m-%dT%H:%M:%S.%fZ")
                    currentdate = datetime.now()
                    timediff = currentdate - finisheddate
                    timediffinminute = int(timediff.total_seconds() / 60)
                    log(f"  Continuing with build #{buildid} for {buildtargetid} finished {timediffinminute} minutes ago...", end="")
                    if timediffinminute > CFG['unity']['build_max_age']:
                        if force:
                            log(f" Process forced to continue (--force flag used)", type=LOG_WARNING, nodate=True)
                        else:
                            log(' The build is too old (max ' + str(CFG['unity']['build_max_age']) + 'min)',
                                type=LOG_ERROR,
                                nodate=True)
                            return 8
                    else:
                        log(f"OK", type=LOG_SUCCESS, nodate=True)

                    # store the buildtargetid in a txt file for the late cleaning process
                    if not simulate:
                        if os.path.exists(f"{buildpath}/{buildtargetid}_build.txt"):
                            os.remove(f"{buildpath}/{buildtargetid}_build.txt")
                        write_in_file(f"{buildpath}/{buildtargetid}_build.txt", f"{buildtargetid}::{buildid}")

                    zipfile = CFG['basepath'] + '/ucb' + buildtargetid + '.zip'

                    log(f"  Deleting old files in {buildospath}...", end="")
                    if not simulate:
                        if os.path.exists(zipfile):
                            os.remove(zipfile)
                        if os.path.exists(buildospath):
                            shutil.rmtree(buildospath, ignore_errors=True)
                    log("OK", type=LOG_SUCCESS, nodate=True)

                    log('  Downloading the built zip file ' + zipfile + '...', end="")
                    if not simulate:
                        urllib.request.urlretrieve(downloadlink, zipfile)
                    log("OK", type=LOG_SUCCESS, nodate=True)

                    log('  Extracting the zip file in ' + buildospath + '...', end="")
                    if not simulate:
                        with ZipFile(zipfile, "r") as zipObj:
                            zipObj.extractall(buildospath)
                            log("OK", type=LOG_SUCCESS, nodate=True)
                    else:
                        log("OK", type=LOG_SUCCESS, nodate=True)

                    s3path = 'UCB/unity-builds/' + steam_appbranch + '/ucb' + buildtargetid + '.zip'
                    log('  Uploading copy to S3 ' + s3path + ' ...', end="")
                    if not simulate:
                        ok = s3_upload_file(zipfile, CFG['aws']['s3bucket'], s3path)
                    else:
                        ok = 0

                    if ok != 0:
                        log('Error uploading file "ucb' + buildtargetid + '.zip" to AWS ' + s3path + '. Check the IAM permissions',
                            type=LOG_ERROR, nodate=True)
                        return 9
                    log("OK", type=LOG_SUCCESS, nodate=True)

    log("--------------------------------------------------------------------------", nodate=True)
    log("Get version from source file...")
    for package, packagevalue in packagecomplete.items():
        for build in packagevalue['builds']:
            buildtargetid = build['buildtargetid']
            buildospath = buildpath + '/' + buildtargetid

            if steam_appversion == "":
                log('  Get the version of the build from files...', end="")
                pathFileVersion = glob.glob(buildospath + "/**/UCB_version.txt", recursive=True)

                if len(pathFileVersion) == 1:
                    if os.path.exists(pathFileVersion[0]):
                        steam_appversion = read_from_file(pathFileVersion[0])
                        steam_appversion = steam_appversion.rstrip('\n')
                        if not simulate:
                            os.remove(pathFileVersion[0])

                    if steam_appversion != "":
                        log(" " + steam_appversion + " ", type=LOG_INFO, nodate=True, end="")
                        log("OK ", type=LOG_SUCCESS, nodate=True)
                else:
                    log(f"File version UCB_version.txt was not found in build directory {buildospath}",
                        type=LOG_WARNING, nodate=True)

    if not noupload:
        log("--------------------------------------------------------------------------", nodate=True)
        log("Uploading files to stores...")
        # ---------------------------------------------------
        # STEAM PROCESS
        # ---------------------------------------------------
        # create the structure used to identify the upload success for a complete package
        for package, packagevalue in steampackages.items():
            if packagecomplete[package]['steam'] == True:
                if package not in packageuploadsuccess:
                    packageuploadsuccess[package] = dict()

                for buildtarget in CFG['buildtargets']:
                    for buildtargetid in buildtarget.keys():
                        if 'steam' in buildtarget[buildtargetid]:
                            if buildtarget[buildtargetid]['steam']['package'] == package:
                                if buildtargetid not in packageuploadsuccess[package]:
                                    packageuploadsuccess[package][buildtargetid] = dict()
                                packageuploadsuccess[package][buildtargetid]['steam'] = False

        first = True
        for package in steampackages.keys():
            # we only want to build the packages that are complete
            if packagecomplete[package]['steam'] == True:
                log(f'Starting Steam process for package {package}...')
                app_id = ""

                for buildtargetid in steampackages[package].keys():
                    # TODO
                    # filter on the platforme we want (if platform is empty, it means that we must do it for all
                    # if build['platform'] == platform or platform == "":
                    # store the data necessary for the next steps

                    # find the data related to the branch we want to build
                    for buildtarget in CFG['buildtargets']:
                        if buildtargetid in buildtarget.keys():
                            if 'steam' in buildtarget[buildtargetid]:
                                package = buildtarget[buildtargetid]['steam']['package']
                                depot_id = buildtarget[buildtargetid]['steam']['depot_id']
                                branch_name = buildtarget[buildtargetid]['steam']['branch_name']
                                live = buildtarget[buildtargetid]['steam']['live']

                                # now prepare the steam files
                                # first time we loop: prepare the main steam file
                                if first:
                                    first = False

                                    app_id = buildtarget[buildtargetid]['steam']['app_id']
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

                                        if nolive == 'false' and branch_name != 'default':
                                            replace_in_file(f"{CFG['basepath']}/Steam/scripts/app_build_{app_id}.vdf",
                                                            "%live%", branch_name)
                                        else:
                                            replace_in_file(f"{CFG['basepath']}/Steam/scripts/app_build_{app_id}.vdf",
                                                            "%live%", "")
                                    log("OK", type=LOG_SUCCESS, nodate=True)

                                    # then the depot files
                                log(f' Preparing platform Steam file for depot {depot_id} / {buildtargetid}...', end="")
                                if not simulate:
                                    shutil.copyfile(f"{CFG['basepath']}/Steam/scripts/template_depot_build_buildtarget.vdf",
                                                f"{CFG['basepath']}/Steam/scripts/depot_build_{buildtargetid}.vdf")

                                    replace_in_file(f"{CFG['basepath']}/Steam/scripts/depot_build_{buildtargetid}.vdf",
                                                    "%depot_id%", depot_id)
                                    replace_in_file(f"{CFG['basepath']}/Steam/scripts/depot_build_{buildtargetid}.vdf",
                                                    "%buildtargetid%", buildtargetid)
                                    replace_in_file(f"{CFG['basepath']}/Steam/scripts/depot_build_{buildtargetid}.vdf",
                                                    "%basepath%", CFG['basepath'])

                                    data = vdf.load(open(f"{CFG['basepath']}/Steam/scripts/app_build_{app_id}.vdf"))
                                    data['appbuild']['depots'][depot_id] = f"depot_build_{buildtargetid}.vdf"

                                    indented_vdf = vdf.dumps(data, pretty=True)

                                    write_in_file(f"{CFG['basepath']}/Steam/scripts/app_build_{app_id}.vdf",
                                                  indented_vdf)

                                packageuploadsuccess[package][buildtargetid]['steam'] = True

                                log("OK", type=LOG_SUCCESS, nodate=True)

                log(" Building Steam packages...", end="")
                if app_id != "":
                    cmd = f'{CFG["basepath"]}/Steam/steamcmd/steamcmd.sh +login "{CFG["steam"]["user"]}" "{CFG["steam"]["password"]}" +run_app_build {CFG["basepath"]}/Steam/scripts/app_build_{app_id}.vdf +quit'
                    if not simulate:
                        ok = os.system(cmd)
                    else:
                        ok = 0

                    if ok != 0:
                        log(f" Executing the bash file {CFG['basepath']}/Steam/steamcmd/steamcmd.sh (exitcode={ok})", type=LOG_ERROR, nodate=True)
                        return 9
                    log("OK", type=LOG_SUCCESS, nodate=True)

                    if simulate:
                        log("  " + cmd)
                else:
                    log("app_id is empty", type=LOG_ERROR, nodate=True)
                    return 9
            else:
                log(f' Package {package} is not complete and will not be processed for Steam...', type=LOG_WARNING)

        # ---------------------------------------------------
        # BUTLER PROCESS
        # ---------------------------------------------------
        # create the structure used to identify the upload success for a package
        for package, packagevalue in butlerpackages.items():
            if packagecomplete[package]['butler'] == True:
                if package not in packageuploadsuccess:
                    packageuploadsuccess[package] = dict()

                for buildtarget in CFG['buildtargets']:
                    for buildtargetid in buildtarget.keys():
                        if 'butler' in buildtarget[buildtargetid]:
                            if buildtarget[buildtargetid]['butler']['package'] == package:
                                if buildtargetid not in packageuploadsuccess[package]:
                                    packageuploadsuccess[package][buildtargetid] = dict()
                                packageuploadsuccess[package][buildtargetid]['butler'] = False

        for package in butlerpackages.keys():
            # we only want to build the packages that are complete
            if packagecomplete[package]['butler'] == True:
                log(f'Starting Butler process for package {package}...')
                app_id = ""

                for buildtargetid in butlerpackages[package].keys():
                    # TODO
                    # filter on the platforme we want (if platform is empty, it means that we must do it for all
                    # if build['platform'] == platform or platform == "":
                    # store the data necessary for the next steps

                    found = False
                    # find the data related to the branch we want to build
                    for buildtarget in CFG['buildtargets']:
                        if buildtargetid in buildtarget.keys():
                            if 'butler' in buildtarget[buildtargetid]:
                                package = buildtarget[buildtargetid]['butler']['package']
                                butler_channel = buildtarget[buildtargetid]['butler']['channel']
                                buildpath = f"{CFG['basepath']}/Steam/build/{buildtargetid}"

                                log(f" Building itch.io(Butler) {buildtargetid} packages...", end="")
                                cmd = f"{CFG['basepath']}/Butler/butler push {buildpath} {CFG['butler']['org']}/{CFG['butler']['project']}:{butler_channel} --userversion={steam_appversion} --if-changed"
                                if not simulate:
                                    ok = os.system(cmd)
                                else:
                                    ok = 0

                                if ok != 0:
                                   log(f"Executing Butler {CFG['basepath']}/Butler/butler (exitcode={ok})", type=LOG_ERROR)
                                   return 10

                                found = True

                                packageuploadsuccess[package][buildtargetid]['butler'] = True

                                log("OK", type=LOG_SUCCESS, nodate=True)

                                if simulate:
                                    log("  " + cmd)

                    if not found:
                        log(f"There is no Butler configuration for the target {buildtargetid}", type=LOG_WARNING)
            else:
                log(f' Package {package} is not complete and will not be processed for Butler...', type=LOG_WARNING)

    if not noclean:
        log("--------------------------------------------------------------------------", nodate=True)
        log("Cleaning successfully upload build in UCB...")
        # let's remove the build successfully uploaded to Steam or Butler from UCB
        directory = f"{CFG['basepath']}/Steam/build"
        # if sum(1 for e in os.scandir(directory)) != 6:
        #    log(f"Missing directory/file in {directory} (should have 6). Aborting...", type=LOG_ERROR, nodate=True)
        #    return 11

        # clean only the packages that are successfull
        for package, packagevalue in packageuploadsuccess.items():
            complete = True
            for buildtarget, buildtargetvalue in packagevalue.items():
                for uploadprocess, uploadprocessvalue in buildtargetvalue.items():
                    if uploadprocessvalue == False:
                        complete = False

            if complete == True:
                log(f" Cleaning package {package}...")
                # cleanup everything related to this package

                for build in builds['success'] + builds['building'] + builds['failure'] + builds['canceled']:
                    for buildtarget in packagevalue.keys():
                        if build['buildtargetid'] == buildtarget:
                            buildid = build['build']
                            log(f"  Deleting build #{buildid} for buildtarget {buildtarget} (status: {build['buildStatus']})...", end="")
                            if not simulate:
                                delete_build(buildtarget, buildid)
                            log("OK", type=LOG_SUCCESS, nodate=True)

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
        exit

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
                                    "force", "install", "simulate", "platform=", "branch=", "version=", "steamappid=", "steamuser=",
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
