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
    #let's filter the result on the requested branch only
    for i in reversed(range(0, len(data))):
        build = data[i]
        
        #identify if the build is successfull
        if not "builds" in build:
            #log(f"Missing builds field for {build["buildtargetid"]}", type=LOG_ERROR)
            datatemp.pop(i)
            continue
        
        #filter on branch
        if branch != "":
            if not build['buildtargetid'] == None:
                #the branch name is at the beginning of the build target name (ex: beta-windows-64bit)
                tabtemp = build['buildtargetid'].split("-")
                if(len(tabtemp) > 0):
                    if(tabtemp[0] != branch):
                        #the branch name is different: remove the build from the result
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
                
        #filter on platform
        if platform != "":
            if not build['platform'] == None:
                if(build['platform'] != platform):
                    #the branch name is different: remove the build from the result
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
    #read input file
    fin = open(file, "rt")
    #read file contents to string
    data = fin.read()
    #replace all occurrences of the required string
    data = data.replace(str(haystack), str(needle))
    #close the input file
    fin.close()
    #open the input file in write mode
    fin = open(file, "wt")
    #overrite the input file with the resulting data
    fin.write(data)
    #close the file
    fin.close()

def write_in_file(file, data):
    #open the input file in write mode
    fin = open(file, "wt")
    #overrite the input file with the resulting data
    fin.write(data)
    #close the file
    fin.close()
    
def read_from_file(file):
    #read input file
    fin = open(file, "rt")
    #read file contents to string
    data = fin.read()
    #close the input file
    fin.close()
    return data
    
def send_email(sender, recipients, title, message):
    global CFG
    client = boto3.client("ses",region_name=CFG['aws']['region'])
    try:
        #Provide the contents of the email.
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
    client = boto3.client("s3",region_name=CFG['aws']['region'])
    try:
        #Provide the file information to upload.
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
    client = boto3.client("s3",region_name=CFG['aws']['region'])
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
    client = boto3.client("s3",region_name=CFG['aws']['region'])
    try:
        response = client.put_object(
            Bucket=bucket_name,
            Key=destination,
            Body=filetoupload
        )
        
        return 0
    # Display an error if something goes wrong.	
    except ClientError as e:
        log(e.response['Error']['Message'], type=LOG_ERROR)
        return 450
        
def s3_delete_file(bucket_name, filetodelete):
    global CFG
    client = boto3.client("s3",region_name=CFG['aws']['region'])
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

def log(message, end="\r\n", type=LOG_INFO):
    global DEBUG_FILE
    
    strprint = ""
    strfile = ""
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
    print(f"unity.py --platform=(standalonelinux64, standaloneosxuniversal, standalonewindows64) [--branch=(prod, beta, develop)] [--nolive] [--version=<version>][--install] [--nodownload] [--noupload] [--noclean] [--noshutdown] [--steamuser=<steamuser>] [--steampassword=<steampassword>]")

def main(argv):
    global DEBUG_FILE_NAME
    
    global CFG
    
    log("Settings environment variables...", end="")
    log("OK", type=LOG_SUCCESS)
    
    steam_appbranch = ""
    steam_appversion = ""

    platform = ""
    nodownload = "false"
    noupload = "false"
    noclean = "false"
    noshutdown = "false"
    force = "false"
    install = "false"
    nolive = "false"
    try:
        opts, args = getopt.getopt(argv,"hldocsfip:b:lv:u:a:",["help", "nolive", "nodownload", "noupload", "noclean", "noshutdown", "force", "install", "platform=", "branch=", "version=", "steamuser=", "steampassword="])
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
            if arg != "prod" and arg != "develop" and arg != "beta":
                print_help()
                return 10
            steam_appbranch = arg
        elif opt in ("-i", "--install"):
            nodependencies = "true"
            nodownload = "true"
            noupload = "true"
            noclean = "true"
            noshutdown = "true"
            install = "true"
        elif opt in ("-d", "--nodownload"):
            nodownload = "true"
        elif opt in ("-d", "--noupload"):
            noupload = "true"
        elif opt in ("-d", "--noclean"):
            noclean = "true"
        elif opt in ("-s", "--noshutdown"):
            noshutdown = "true"
        elif opt in ("-f", "--force"):
            force = "true"
        elif opt in ("-l", "--live"):
            nolive = "true"
        elif opt in ("-v", "--version"):
            steam_appversion = arg
        elif opt in ("-u", "--steamuser"):
            CFG['steam']['user'] = arg
        elif opt in ("-a", "--steampassword"):
            CFG['steam']['password'] = arg
    
    buildpath = CFG['basepath'] + '/Steam/build'
    
    #install all the dependencies and test them
    if install == "true":
        log("Updating apt sources...", end="")
        ok = os.system("sudo apt-get update -qq -y > /dev/null 1")
        if ok > 0:
            log("Dependencies installatin failed", type=LOG_ERROR)
            return 210
        log("OK", type=LOG_SUCCESS)
        
        log("Installing dependencies...", end="")
        ok = os.system("sudo apt-get install -qq -y mc python3-pip git lib32gcc1 python3-requests > /dev/null")
        if ok > 0:
            log("Dependencies installatin failed", type=LOG_ERROR)
            return 211
        log("OK", type=LOG_SUCCESS)
        
        log("Installing AWS cli...", end="")
        ok = os.system('curl "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o "' + CFG['basepath'] + '/awscliv2.zip" --silent')
        if ok > 0:
            log("Dependencies installatin failed", type=LOG_ERROR)
            return 212
        ok = os.system('unzip -oq ' + CFG['basepath'] + '/awscliv2.zip -d ' + CFG['basepath'])
        if ok > 0:
            log("Dependencies installatin failed", type=LOG_ERROR)
            return 213
        ok = os.system('rm ' + CFG['basepath'] + '/awscliv2.zip')
        if ok > 0:
            log("Dependencies installatin failed", type=LOG_ERROR)
            return 214
        ok = os.system('sudo ' + CFG['basepath'] + '/aws/install --update')
        if ok > 0:
            log("Dependencies installation failed", type=LOG_ERROR)
            return 215
        log("OK", type=LOG_SUCCESS)
        
        log("Installing python boto3...", end="")
        ok = os.system("sudo pip3 install boto3 > /dev/null")
        if ok > 0:
            log("Dependencies installatin failed", type=LOG_ERROR)
            return 216
        log("OK", type=LOG_SUCCESS)
        
        log("Configuring AWS credentials...", end="")
        if not os.path.exists(CFG['homepath'] + '/.aws'):
            os.mkdir(CFG['homepath'] + '/.aws')
        write_in_file(CFG['homepath'] + '/.aws/config', '[default]\r\nregion=' + CFG['aws']['region'] + '\r\noutput=json\r\naws_access_key_id=' + CFG['aws']['accesskey'] + '\r\naws_secret_access_key=' + CFG['aws']['secretkey'])
        log("OK", type=LOG_SUCCESS)
        
        log("Testing AWS connection...", end="")
        ok = os.system('echo "Success" > ' + CFG['basepath'] + '/test_successfull.txt')
        if ok != 0:
            log("Creating temp file for connection test to AWS", type=LOG_ERROR)
            return 300
        ok = s3_upload_file(CFG['basepath'] + '/test_successfull.txt', 'phoebecoeus.net', 'UCB/steam-parameters/test_successfull.txt')
        if ok != 0:
            log("Error uploading file to AWS UCB/steam-parameters. Check the IAM permissions", type=LOG_ERROR)
            return 301
        ok = s3_delete_file('phoebecoeus.net', 'UCB/steam-parameters/test_successfull.txt')
        if ok != 0:
            log("Error deleting file from AWS UCB/steam-parameters. Check the IAM permissions", type=LOG_ERROR)
            return 302
        ok = s3_upload_file(CFG['basepath'] + '/test_successfull.txt', 'phoebecoeus.net', 'UCB/unity-builds/test_successfull.txt')
        if ok != 0:
            log("Error uploading file to AWS UCB/unity-builds. Check the IAM permissions", type=LOG_ERROR)
            return 303
        ok = s3_delete_file('phoebecoeus.net', 'UCB/unity-builds/test_successfull.txt')
        if ok != 0:
            log("Error deleting file from AWS UCB/unity-builds. Check the IAM permissions", type=LOG_ERROR)
            return 302
        ok = os.system('rm ' + CFG['basepath'] + '/test_successfull.txt')
        if ok != 0:
            log("Error deleting after connecting to AWS", type=LOG_ERROR)
            return 304
        log("OK", type=LOG_SUCCESS)
        
        log("Installing UCB-steam startup script...", end="")
        shutil.copyfile(CFG['basepath'] + '/UCB-steam-startup-script.example', CFG['basepath'] + '/UCB-steam-startup-script')
        replace_in_file(CFG['basepath'] + '/UCB-steam-startup-script', '%basepath%', CFG['basepath'])
        ok = os.system('sudo mv ' + CFG['basepath'] + '/UCB-steam-startup-script /etc/init.d/UCB-steam-startup-script > /dev/null')
        if ok != 0:
            log("Error copying UCB-steam startup script file to /etc/init.d", type=LOG_ERROR)
            return 310
        ok = os.system('sudo chown root:root /etc/init.d/UCB-steam-startup-script ; sudo chmod 755 /etc/init.d/UCB-steam-startup-script ; sudo systemctl daemon-reload > /dev/null')
        if ok > 0:
            log("Error setting permission to UCB-steam startup script file", type=LOG_ERROR)
            return 311
        log("OK", type=LOG_SUCCESS)
    
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
        log("OK", type=LOG_SUCCESS)
        
        #log("Download dependencies from S3...", end="")
        #ok = s3_download_directory("UCB/steam-scripts/scripts", "phoebecoeus.net", f"{CFG['basepath']}/Steam/scripts")
        #if ok != 0:
        #    log("Error getting Steam template files from S3", type=LOG_ERROR)
        #    return 20
        #log("OK", type=LOG_SUCCESS)
    
        log("Testing UCB connection...", end="")
        buildtargets = get_last_builds(steam_appbranch, platform)
        if buildtargets == None:
            log("Error connecting to UCB", type=LOG_ERROR)
            return 21
        log("OK", type=LOG_SUCCESS)
        
        log("Downloadng Steamworks SDK...", end="")
        if not os.path.exists(f"{CFG['basepath']}/Steam/steamcmd/linux32/steamcmd"):
            ok = s3_download_directory("UCB/steam-sdk", "phoebecoeus.net", f"{CFG['basepath']}/steam-sdk")
            if ok != 0:
                log("Error getting files from S3", type=LOG_ERROR)
                return 22
            
            shutil.copytree(f"{CFG['basepath']}/steam-sdk/builder_linux", f"{CFG['basepath']}/Steam/steamcmd", dirs_exist_ok=True)
            st = os.stat(f"{CFG['basepath']}/Steam/steamcmd/steamcmd.sh")
            os.chmod(f"{CFG['basepath']}/Steam/steamcmd/steamcmd.sh", st.st_mode | stat.S_IEXEC)
            st = os.stat(f"{CFG['basepath']}/Steam/steamcmd/linux32/steamcmd")
            os.chmod(f"{CFG['basepath']}/Steam/steamcmd/linux32/steamcmd", st.st_mode | stat.S_IEXEC)
            shutil.rmtree(f"{CFG['basepath']}/steam-sdk")
            log("OK", type=LOG_SUCCESS)
        else:
            log("OK (dependencie already met)", type=LOG_SUCCESS)
    
        log("Testing Steam connection...", end="")
        ok = os.system(CFG['basepath'] + '/Steam/steamcmd/steamcmd.sh +login "' + CFG['steam']['user'] + '" "' + CFG['steam']['password'] + '" +quit')
        if ok != 0:
            log("Error connecting to Steam", type=LOG_ERROR)
            return 23
        log("OK", type=LOG_SUCCESS)
        
        log("Testing email notification...", end="")
        strLog = '<b>Result of the UCB-steam script installation:</b>\r\n</br>\r\n</br>'
        strLog = strLog + read_from_file(DEBUG_FILE_NAME)
        strLog = strLog + '\r\n</br>\r\n</br><font color="GREEN">Everything is set up correctly. Congratulations !</font>'
        ok = send_email(CFG['email']['from'], CFG['email']['recipients'], "Steam build notificaiton test", strLog)
        if ok != 0:
            log("Error sending email", type=LOG_ERROR)
            return 24
        log("OK", type=LOG_SUCCESS)
        
        log("Everything is set up correctly. Congratulations !", type=LOG_SUCCESS)
        
        return 0
    
    #get the information from S3 about the branch and the version
    log("Getting branch and version from AWS S3...", end="")
    parameterfile = CFG['basepath'] + '/UCB-parameters.conf'
    if (steam_appbranch == "" or steam_appversion == ""):
        ok = s3_download_file("UCB/steam-parameters/UCB-parameters.conf", CFG['aws']['s3bucket'], parameterfile)
        if ok != 0:
            log("Error downloading UCB/steam-parameters/UCB-parameters.conf from AWS S3", type=LOG_ERROR)
            return 20
        strParam = read_from_file(parameterfile)
        arrParam = strParam.split(',')
        if len(arrParam) >= 2:
            if steam_appbranch == "":
                steam_appbranch = arrParam[0]
            if steam_appversion == "":
                steam_appversion = arrParam[1]
        else:
            log('Error reading parameters from ' + parameterfile + ': not enough parameters', type=LOG_ERROR)
            return 30
        log('OK (branch=' + steam_appbranch + ', version=' + steam_appversion + ')', type=LOG_SUCCESS)
    else:
        log("OK (provided through parameters)", type=LOG_SUCCESS)
    
    #Get all the successfull builds from Unity Cloud Build
    filter = f"Filtering on branch:{steam_appbranch}"
    if platform != "":
        filter = f"{filter} and platform:{platform}"
    log(f"Retrieving all the builds information ({filter})...", end="")
    buildtargets = get_last_builds(steam_appbranch, platform)
    if len(buildtargets) == 0:
        log("Retrieving the information. No build available in UCB", type=LOG_ERROR)
        return 3
    if len(buildtargets) != 3 and platform == "":
        log(f"There must be 3 successul build ({len(buildtargets)} for now)", type=LOG_ERROR)
        if force == "true":
            log(f"Process forced to continue (--force flag used)", type=LOG_WARNING)
        else:
            return 4
    log("OK", type=LOG_SUCCESS) 
    
    #download the builds from UCB
    if nodownload == "false":
        for build in buildtargets:
            #filter on the platforme we want (if platform is empty, it means that we must do it for all
            if build['platform'] == platform or platform == "":
                #store the data necessary for the next steps
                name = build['name']
                buildtargetid = build['buildtargetid']
                platformtemp = build['platform']
                buildospath = buildpath + '/' + platformtemp
                
                if name == "" or buildtargetid == "" or platformtemp == "":
                    log(" Missing field", type=LOG_ERROR)
                    return 5
                
                if os.path.exists(f"{buildospath}/build.txt"):
                    os.remove(f"{buildospath}/build.txt")
                
                log(f" Preparing {platformtemp}") 
                if not "builds" in build:
                    log(" Missing builds field", type=LOG_ERROR)
                    return 6
                downloadlink = build['builds'][0]['links']['download_primary']['href']
                buildid =  build['builds'][0]['build']
                
                if build['builds'][0]['finished'] == "":
                    log(" The build seems to be a failed one", type=LOG_ERROR)
                    return 7
                finisheddate = datetime.strptime(build['builds'][0]['finished'], "%Y-%m-%dT%H:%M:%S.%fZ")
                currentdate = datetime.now()
                timediff = currentdate - finisheddate
                timediffinminute = int(timediff.total_seconds() / 60)
                log(f"  Continuing with build #{buildid} for {buildtargetid} finished {timediffinminute} minutes ago...") 
                if timediffinminute > 120:
                    log(" The build is too old", type=LOG_ERROR)
                    if force == "true":
                        log(f"Process forced to continue (--force flag used)", type=LOG_WARNING)
                    else:
                        return 8
                
                #store the buildtargetid in a txt file for the late cleaning process
                if os.path.exists(f"{buildpath}/{platformtemp}_build.txt"):
                    os.remove(f"{buildpath}/{platformtemp}_build.txt")
                write_in_file(f"{buildpath}/{platformtemp}_build.txt", f"{buildtargetid}::{buildid}")
                
                zipfile = CFG['basepath'] + '/ucb' + platformtemp + '.zip'
                
                log(f"  Deleting old files in {buildospath}...", end="")
                if os.path.exists(zipfile):
                    os.remove(zipfile)
                if os.path.exists(buildospath):
                    shutil.rmtree(buildospath, ignore_errors=True)
                log("OK", type=LOG_SUCCESS) 
                
                log("  Downloading the built zip file...", end="") 
                urllib.request.urlretrieve(downloadlink, zipfile)
                log("OK", type=LOG_SUCCESS) 
                
                log("  Extracting the zip file...", end="") 
                with ZipFile(zipfile, "r") as zipObj:
                    zipObj.extractall(f"{buildospath}")
                    log("OK", type=LOG_SUCCESS)
        
                log("  Uploading copy to S3...", end="")
                ok = s3_upload_file(zipfile, 'phoebecoeus.net', 'UCB/unity-builds/' + steam_appbranch + '/ucb' + platformtemp + '.zip')
                if ok != 0:
                    log('Error uploading file "ucb' + platformtemp + '.zip" to AWS UCB/unity-builds. Check the IAM permissions', type=LOG_ERROR)
                    return 9
                
                log("  Cleaning zip file...", end="")
                os.remove(zipfile)
                log("OK", type=LOG_SUCCESS)
                
                log("")
        
    
    if noupload == "false":
        #now prepare the steam files
        log("Preparing Steam files...", end="") 
        shutil.copyfile(f"{CFG['basepath']}/Steam/scripts/template_app_build.vdf", f"{CFG['basepath']}/Steam/scripts/app_build_{CFG['steam']['appid']}.vdf")
        shutil.copyfile(f"{CFG['basepath']}/Steam/scripts/template_depot_build_standalonelinux64.vdf", f"{CFG['basepath']}/Steam/scripts/depot_build_standalonelinux64.vdf")
        shutil.copyfile(f"{CFG['basepath']}/Steam/scripts/template_depot_build_standaloneosxuniversal.vdf", f"{CFG['basepath']}/Steam/scripts/depot_build_standaloneosxuniversal.vdf")
        shutil.copyfile(f"{CFG['basepath']}/Steam/scripts/template_depot_build_standalonewindows64.vdf", f"{CFG['basepath']}/Steam/scripts/depot_build_standalonewindows64.vdf")
        
        replace_in_file(f"{CFG['basepath']}/Steam/scripts/app_build_{CFG['steam']['appid']}.vdf", "%basepath%", CFG['basepath'])
        replace_in_file(f"{CFG['basepath']}/Steam/scripts/app_build_{CFG['steam']['appid']}.vdf", "%Version%", steam_appversion)
        replace_in_file(f"{CFG['basepath']}/Steam/scripts/app_build_{CFG['steam']['appid']}.vdf", "%Branch%", steam_appbranch)
        replace_in_file(f"{CFG['basepath']}/Steam/scripts/app_build_{CFG['steam']['appid']}.vdf", "%AppID%", CFG['steam']['appid'])
        replace_in_file(f"{CFG['basepath']}/Steam/scripts/app_build_{CFG['steam']['appid']}.vdf", "%AppDepotWindows%", CFG['steam']['appid_windows'])
        replace_in_file(f"{CFG['basepath']}/Steam/scripts/app_build_{CFG['steam']['appid']}.vdf", "%AppDepotLinux%", CFG['steam']['appid_linux'])
        replace_in_file(f"{CFG['basepath']}/Steam/scripts/app_build_{CFG['steam']['appid']}.vdf", "%AppDepotMacos%", CFG['steam']['appid_macos'])
        
        replace_in_file(f"{CFG['basepath']}/Steam/scripts/depot_build_standalonewindows64.vdf", "%AppDepotWindows%", CFG['steam']['appid_windows'])
        replace_in_file(f"{CFG['basepath']}/Steam/scripts/depot_build_standalonelinux64.vdf", "%AppDepotLinux%", CFG['steam']['appid_linux'])
        replace_in_file(f"{CFG['basepath']}/Steam/scripts/depot_build_standaloneosxuniversal.vdf", "%AppDepotMacos%", CFG['steam']['appid_macos'])
        
        if nolive == 'false' and steam_appbranch != 'prod':
            replace_in_file(f"{CFG['basepath']}/Steam/scripts/app_build_{CFG['steam']['appid']}.vdf", "%BranchLive%", steam_appbranch)
        else:
            replace_in_file(f"{CFG['basepath']}/Steam/scripts/app_build_{CFG['steam']['appid']}.vdf", "%BranchLive%", "")
        log("OK", type=LOG_SUCCESS) 
    
        log("Building Steam packages...", end="")
        ok = os.system(CFG['basepath'] + '/Steam/steamcmd/steamcmd.sh +login "' + CFG['steam']['user'] + '" "' + CFG['steam']['password'] + '" +run_app_build ' + CFG['basepath'] + '/Steam/scripts/app_build_1121200.vdf +quit')
        if ok != 0:
            log(f"Executing the bash file {CFG['basepath']}/Steam/steamcmd/steamcmd.sh (exitcode={ok})", type=LOG_ERROR)
            return 9
        log("OK", type=LOG_SUCCESS)
    
    if noclean == "false":
        log("Cleaning successfully upload build in UCB...") 
        #let's remove the build successfully uploaded to steam from UCB
        directory = f"{CFG['basepath']}/Steam/build"
        if sum(1 for e in os.scandir(directory)) != 6:
            log(f"Missing directory/file in {directory} (should have 6). Aborting...", type=LOG_ERROR)
            return 11
        
        for file in os.scandir(directory):
            if file.is_file():
                data = read_from_file(file.path)
                strsplit = data.split("::")
                buildtargetid = strsplit[0]
                build = strsplit[1]
                
                log(f" Deleting build #{build} for buildtarget {buildtargetid}...", end="")
                delete_build(buildtargetid, build)
                os.remove(file.path)
                log("OK", type=LOG_SUCCESS)

    log("All done!")
    return 0
    

if __name__ == "__main__":
    #load the configuration from the config file
    currentpath = os.path.dirname(os.path.abspath(__file__))
    with open(currentpath + '/UCB-steam.config', "r") as ymlfile:
        CFG = yaml.load(ymlfile, Loader=yaml.FullLoader)
    
    if CFG is None:
        codeok = 11
        exit

    #create the log directory if it does not exists
    if not os.path.exists(f"{CFG['logpath']}"):
        os.mkdir(f"{CFG['logpath']}")
    #set the log file name with the current datetime
    DEBUG_FILE_NAME = CFG['logpath'] + '/' + datetime.now().strftime("%Y%m%d_%H%M%S") + '.html'
    #open the logfile for writing
    DEBUG_FILE = open(DEBUG_FILE_NAME, "wt")
    
    codeok = 0
    noshutdown = 'false'
    try:
        opts, args = getopt.getopt(sys.argv[1:],"hldocsfip:b:lv:u:a:",["help", "nolive", "nodownload", "noupload", "noclean", "noshutdown", "force", "install", "platform=", "branch=", "version=", "steamuser=", "steampassword="])
        for opt, arg in opts:
            if opt in ("-s", "--noshutdown"):
                noshutdown = 'true'
            elif opt in ("-i", "--install"):
                noshutdown = 'true'
    except getopt.GetoptError:
        print_help()
        codeok = 11
    
    if codeok != 10 and codeok != 11:
        codeok = main(sys.argv[1:])
        if noshutdown == "false" and codeok != 10:
            log("Shutting down computer...")
            os.system("sudo shutdown +3")
        
    log("--- Script execution time : %s seconds ---" % (time.time() - start_time))
    #close the logfile
    DEBUG_FILE.close()
    if codeok != 10 and codeok != 11:
        send_email(CFG['email']['from'], CFG['email']['recipients'], "Steam build result", read_from_file(DEBUG_FILE_NAME))
   