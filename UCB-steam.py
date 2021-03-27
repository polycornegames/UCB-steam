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

global EMAIL_FROM
global EMAIL_RECIPIENTS

global STEAM_APPID
global STEAM_APPID_DEPOTWINDOWS
global STEAM_APPID_DEPOTLINUX
global STEAM_APPID_DEPOTMACOS
global STEAM_USER
global STEAM_PASSWORD

global UNITYCLOUDBUILD_ORG_ID
global UNITYCLOUDBUILD_PROJECT_ID
global UNITYCLOUDBUILD_API_KEY

global AWS_REGION
global AWS_ACCESSKEY
global AWS_SECRETACCESSKEY
global AWS_S3BUCKET

##########################
#SET YOUR OWN VALUES HERE#
##########################
STEAM_APPID = "1000"
STEAM_APPID_DEPOTWINDOWS = "1001"
STEAM_APPID_DEPOTLINUX = "1002"
STEAM_APPID_DEPOTMACOS = "1003"
STEAM_USER = 'darthvadorPGM'
STEAM_PASSWORD = 'sidiousalways2nd'
    
EMAIL_FROM = 'steambuild@empire.org'
EMAIL_RECIPIENTS = ['darthvador@empire.org','generaltarkin@empire.org']

UNITYCLOUDBUILD_ORG_ID = "4815162342"
UNITYCLOUDBUILD_PROJECT_ID = "3283627-c3po-r2d2-bb8-tk421"
UNITYCLOUDBUILD_API_KEY = "a6a5fa03a9b8711code66cd467836a4"

AWS_REGION = "eu-west-1"
AWS_ACCESSKEY = "OSDFUZEOIUZAPOIRIOUIUEZR"
AWS_SECRETACCESSKEY = "YmKphQIUoXkyvZorr1Oak5Yd30IIhk1n7nwf4WgI"
AWS_S3BUCKET = "empire.org"
##########################

def api_url():
    global UNITYCLOUDBUILD_ORG_ID
    global UNITYCLOUDBUILD_PROJECT_ID
    return 'https://build-api.cloud.unity3d.com/api/v1/orgs/{}/projects/{}'.format(UNITYCLOUDBUILD_ORG_ID,
                                                                                   UNITYCLOUDBUILD_PROJECT_ID)


def headers():
    global UNITYCLOUDBUILD_API_KEY
    return {'Authorization': 'Basic {}'.format(UNITYCLOUDBUILD_API_KEY)}


def create_new_build_target(data, branch, user):
    name_limit = 64 - 17 - len(user)
    name = re.sub('[^0-9a-zA-Z]+', '-', branch)[0:name_limit]

    data['name'] = 'Autobuild of {} by {}'.format(name, user)
    data['settings']['scm']['branch'] = branch

    url = '{}/buildtargets'.format(api_url())
    response = requests.post(url, headers=headers(), json=data)

    if not response.ok:
        logging.error('Creating build target "' + data['name'] + '" failed', response.text)

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
    global UNITYCLOUDBUILD_ORG_ID
    global UNITYCLOUDBUILD_PROJECT_ID
    return 'https://developer.cloud.unity3d.com/build/orgs/{}/projects/{}/buildtargets/{}/builds/{}/log/compact/'.format(
        UNITYCLOUDBUILD_ORG_ID, UNITYCLOUDBUILD_PROJECT_ID, buildtarget_id, build_number
    )
    
def get_last_builds(branch="", platform=""):
    url = '{}/buildtargets?include_last_success=true'.format(api_url())
    response = requests.get(url, headers=headers())
    
    datatemp = []
    
    if not response.ok:
        log(f'Getting build template failed: {response.text}', type=LOG_ERROR)
        return datatemp

    data = response.json()
    datatemp = copy.deepcopy(data)
    #let's filter the result on the requested branch only
    for i in reversed(range(0, len(data))):
        build = data[i]
        
        #identify if the build is successfull
        if not "builds" in build:
            #log(f'Missing builds field for {build["buildtargetid"]}', type=LOG_ERROR)
            datatemp.pop(i)
            continue
        
        #filter on branch
        if branch != "":
            if not build['buildtargetid'] == None:
                #the branch name is at the beginning of the build target name (ex: beta-windows-64bit)
                tabtemp = build['buildtargetid'].split('-')
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
        log(f'Deleting build target failed: {response.text}', type=LOG_ERROR)

    return deleted

def replace_in_file(file, haystack, needle):
    #read input file
    fin = open(file, "rt")
    #read file contents to string
    data = fin.read()
    #replace all occurrences of the required string
    data = data.replace(haystack, needle)
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
    global AWS_REGION
    client = boto3.client('ses',region_name=AWS_REGION)
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

def upload_file(file, bucket):
    global AWS_REGION
    client = boto3.client('s3',region_name=AWS_REGION)
    try:
        #Provide the file information to upload.
        response = client.upload_file(
            Filename=file,
            Bucket=bucket,
            Key=file,
        )
        return 0
    # Display an error if something goes wrong.	
    except ClientError as e:
        log(e.response['Error']['Message'], type=LOG_ERROR)
        return 450

def download_file(file, bucket, destination):
    global AWS_REGION
    client = boto3.client('s3',region_name=AWS_REGION)
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
        
def download_directory(directory, bucket_name, destination):
    global AWS_REGION
    client = boto3.client('s3',region_name=AWS_REGION)
    s3 = boto3.resource('s3')
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

def log(message, end="\r\n", type=LOG_INFO):
    global DEBUG_FILE
    
    strprint = ""
    strfile = ""
    if type == LOG_ERROR:
        strprint = strprint + f'{Fore.RED}'
        strprint = strprint + "ERROR: "
        strfile = strfile + '<font color="red">'
        strfile = strfile + "ERROR: "
    elif type == LOG_WARNING:
        strprint = strprint + f'{Fore.YELLOW}'
        strprint = strprint + "WARNING: "
        strfile = strfile + '<font color="yellow">'
        strfile = strfile + "WARNING: "
    elif type == LOG_SUCCESS:
        strprint = strprint + f'{Fore.GREEN}'
        strfile = strfile + '<font color="green">'
    
    strprint = strprint + message
    strfile = strfile + message
    
    if type == LOG_ERROR or type == LOG_WARNING or type == LOG_SUCCESS:
        strprint = strprint + f'{Style.RESET_ALL}'
        strfile = strfile + '</font>'
    
    if end == "":
        print(strprint, end="")
    else:
        print(strprint)
    if not DEBUG_FILE.closed:
        if end == "":
            DEBUG_FILE.write(strfile)
        else:
            DEBUG_FILE.write(strfile + '</br>' + end)
        
def print_help():
    print(f'unity.py --platform=(standalonelinux64, standaloneosxuniversal, standalonewindows64) [--branch=(prod, beta, develop)] [--nolive] [--version=<version>][--install] [--nodependencies] [--nodownload] [--noupload] [--noclean] [--noshutdown] [--steamuser=<steamuser>] [--steampassword=<steampassword>]')

def main(argv):
    global DEBUG_FILE_NAME
    
    global STEAM_USER
    global STEAM_PASSWORD
    
    global EMAIL_FROM
    global EMAIL_RECIPIENTS
    
    global UNITYCLOUDBUILD_API_KEY
    global UNITYCLOUDBUILD_ORG_ID
    global UNITYCLOUDBUILD_PROJECT_ID
    
    global AWS_REGION
    global AWS_ACCESSKEY
    global AWS_SECRETACCESSKEY
    global AWS_S3BUCKET
    
    log('Settings environment variables...', end="")
    log('OK', type=LOG_SUCCESS) 
        
    STEAM_APPVERSION = '0.30'
    STEAM_APPBRANCH = 'develop'

    platform = ""
    nodependencies = "false"
    nodownload = "false"
    noupload = "false"
    noclean = "false"
    noshutdown = "false"
    force = "false"
    install = "false"
    nolive = "false"
    try:
        opts, args = getopt.getopt(argv,"hlndocsfip:b:lv:u:a:",["help", "nolive", "nodependencies", "nodownload", "noupload", "noclean", "noshutdown", "force", "install", "platform=", "branch=", "version=", "steamuser=", "steampassword="])
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
            STEAM_APPBRANCH = arg
        elif opt in ("-i", "--install"):
            nodependencies = 'true'
            nodownload = 'true'
            noupload = 'true'
            noclean = 'true'
            noshutdown = 'true'
            install = 'true'
        elif opt in ("-n", "--nodependencies"):
            nodependencies = 'true'
        elif opt in ("-d", "--nodownload"):
            nodownload = 'true'
        elif opt in ("-d", "--noupload"):
            noupload = 'true'
        elif opt in ("-d", "--noclean"):
            noclean = 'true'
        elif opt in ("-s", "--noshutdown"):
            noshutdown = 'true'
        elif opt in ("-f", "--force"):
            force = 'true'
        elif opt in ("-l", "--live"):
            nolive = 'true'
        elif opt in ("-v", "--version"):
            STEAM_APPVERSION = arg
        elif opt in ("-u", "--steamuser"):
            STEAM_USER = arg
        elif opt in ("-a", "--steampassword"):
            STEAM_PASSWORD = arg
    
    buildpath = '/home/ubuntu/Steam/build'
    #platform = 'standalonewindows64'
    
    if nodependencies == "false":
        log('Installing dependencies...', end="") 
        ok = os.system('/home/ubuntu/installDependenciesSteam.sh')
        if ok > 0:
            log('Executing the bash file for dependencies installation: /home/ubuntu/installDependenciesSteam.sh', type=LOG_ERROR)
            return 2
        log('OK', type=LOG_SUCCESS)
        
    #install all the dependencies and test them
    if install == "true":
        log('Updating apt sources...', end="")
        ok = os.system('sudo apt-get update -qq -y > /dev/null 1')
        if ok > 0:
            log('Dependencies installatin failed', type=LOG_ERROR)
            return 210
        log('OK', type=LOG_SUCCESS)
        
        log('Installing dependencies...', end="")
        ok = os.system('sudo apt-get install -qq -y mc python3-pip git lib32gcc1 python3-requests > /dev/null')
        if ok > 0:
            log('Dependencies installatin failed', type=LOG_ERROR)
            return 211
        log('OK', type=LOG_SUCCESS)
        
        log('Installing AWS cli...', end="")
        ok = os.system('curl "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o "awscliv2.zip" --silent')
        if ok > 0:
            log('Dependencies installatin failed', type=LOG_ERROR)
            return 212
        ok = os.system('unzip -oq /home/ubuntu/awscliv2.zip -d /home/ubuntu')
        if ok > 0:
            log('Dependencies installatin failed', type=LOG_ERROR)
            return 213
        ok = os.system('sudo /home/ubuntu/aws/install --update')
        if ok > 0:
            log('Dependencies installatin failed', type=LOG_ERROR)
            return 214
        log('OK', type=LOG_SUCCESS)
        
        log('Installing python boto3...', end="")
        ok = os.system('sudo pip3 install boto3 > /dev/null')
        if ok > 0:
            log('Dependencies installatin failed', type=LOG_ERROR)
            return 215
        log('OK', type=LOG_SUCCESS)
        
        log('Configuring AWS credentials...', end="")
        if not os.path.exists('/home/ubuntu/.aws'):
            os.mkdir('/home/ubuntu/.aws')
        write_in_file('/home/ubuntu/.aws/config', f'[default]\r\nregion={AWS_REGION}\r\noutput=json\r\naws_access_key_id={AWS_ACCESSKEY}\r\naws_secret_access_key={AWS_SECRETACCESSKEY}')
        log('OK', type=LOG_SUCCESS)
        
        log('Testing AWS connection...', end="")
        ok = download_file('UCB/deploy-scripts/installDependenciesSteam.sh', 'phoebecoeus.net', '/home/ubuntu/installDependenciesSteam.sh')
        if ok != 0:
            log('Error connecting to AWS', type=LOG_ERROR)
            return 300
        log('OK', type=LOG_SUCCESS)
        
        log('Installing UCB-steam startup script...', end="")
        #TODO download from git
        ok = download_file('UCB/deploy-scripts/UCB-steam-startup-script', 'phoebecoeus.net', '/etc/init.d/UCB-steam-startup-script')
        if ok != 0:
            log('Error getting UCB-steam startup script file from S3', type=LOG_ERROR)
            return 310
        ok = os.system('sudo chmod +x /etc/init.d/UCB-steam-startup-script ; systemctl daemon-reload > /dev/null')
        if ok > 0:
            log('Error setting permission to UCB-steam startup script file', type=LOG_ERROR)
            return 311
        log('OK', type=LOG_SUCCESS)
    
        log('Creating folder structure for Steamworks...', end="")
        if not os.path.exists('/home/ubuntu/Steam'):
            os.mkdir('/home/ubuntu/Steam')
        if not os.path.exists('/home/ubuntu/Steam/build'):
            os.makedir('/home/ubuntu/Steam/build')
        if not os.path.exists('/home/ubuntu/Steam/output'):
            os.makedir('/home/ubuntu/Steam/output')
        if not os.path.exists('/home/ubuntu/Steam/scripts'):
            os.makedir('/home/ubuntu/Steam/scripts')
        if not os.path.exists('/home/ubuntu/Steam/steamcmd'):
            os.makedir('/home/ubuntu/Steam/steamcmd')
        log('OK', type=LOG_SUCCESS)
        
        log('Download dependencies from S3...', end="")
        ok = download_directory('UCB/steam-scripts/scripts/template_', 'phoebecoeus.net', '/home/ubuntu/Steam/scripts')
        if ok != 0:
            log('Error getting Steam template files from S3', type=LOG_ERROR)
            return 20
        log('OK', type=LOG_SUCCESS)
    
        log('Testing UCB connection...', end="")
        buildtargets = get_last_builds(STEAM_APPBRANCH, platform)
        if buildtargets == None:
            log('Error connecting to UCB', type=LOG_ERROR)
            return 21
        log('OK', type=LOG_SUCCESS)
        
        log('Downloadng Steamworks SDK...', end="")
        if not os.path.exists('/home/ubuntu/Steam/steamcmd/linux32/steamcmd'):
            ok = download_directory('UCB/steam-sdk', 'phoebecoeus.net', '/home/ubuntu/steamsdk')
            if ok != 0:
                log('Error getting files from S3', type=LOG_ERROR)
                return 22
            
            shutil.copytree('/home/ubuntu/steamsdk/builder_linux', '/home/ubuntu/Steam/steamcmd', dirs_exist_ok=True)
            st = os.stat('/home/ubuntu/Steam/steamcmd/steamcmd.sh')
            os.chmod('/home/ubuntu/Steam/steamcmd/steamcmd.sh', st.st_mode | stat.S_IEXEC)
            st = os.stat('/home/ubuntu/Steam/steamcmd/linux32/steamcmd')
            os.chmod('/home/ubuntu/Steam/steamcmd/linux32/steamcmd', st.st_mode | stat.S_IEXEC)
        log('OK', type=LOG_SUCCESS)
    
        log('Testing Steam connection...', end="")
        ok = os.system(f'/home/ubuntu/Steam/steamcmd/steamcmd.sh +login "{STEAM_USER}" "{STEAM_PASSWORD}" +quit')
        if ok != 0:
            log('Error connecting to Steam', type=LOG_ERROR)
            return 23
        log('OK', type=LOG_SUCCESS)
        
        log('Testing email notification...', end="")
        ok = send_email(EMAIL_FROM, EMAIL_RECIPIENTS, 'Steam build notificaiton test', 'Everything is set up correctly. Congratulation !')
        if ok != 0:
            log('Error sending email', type=LOG_ERROR)
            return 24
        log('OK', type=LOG_SUCCESS)
        
        log('Everything is set up correctly. Congratulation !', type=LOG_SUCCESS)
        
        return 0
    
    #get the information from S3 about the branch and the version
    log('Getting branch and version from AWS S3...', end="")
    if (STEAM_APPBRANCH == "" or STEAM_APPVERSION == ""):
        ok = download_file('UCB/steam-parameters/parameters.conf', AWS_S3BUCKET, '/home/ubuntu/parameters.conf')
        if ok != 0:
            log('Error downloading UCB/steam-parameters/parameters.conf from AWS S3', type=LOG_ERROR)
            return 20
        strParam = read_from_file('/home/ubuntu/parameters.conf')
        arrParam = strParam.split()
        if len(arrParam) >= 2:
            if STEAM_APPBRANCH == "":
                STEAM_APPBRANCH = arrParam[0]
            if STEAM_APPVERSION == "":
                STEAM_APPVERSION = arrParam[1]
        else:
            log('Error reading parameters from /home/ubuntu/parameters.conf: not enough parameters', type=LOG_ERROR)
            return 30
        log('OK', type=LOG_SUCCESS)
    else:
        log('OK (provided through parameters)', type=LOG_SUCCESS)
    
    #Get all the successfull builds from Unity Cloud Build
    filter = f'Filtering on branch:{STEAM_APPBRANCH}'
    if platform != "":
        filter = f'{filter} and platform:{platform}'
    log(f'Retrieving all the builds information ({filter})...', end="")
    buildtargets = get_last_builds(STEAM_APPBRANCH, platform)
    if len(buildtargets) == 0:
        log('Retrieving the information. No build available in UCB', type=LOG_ERROR)
        if force == "true":
            log(f'Process forced to continue (--force flag used)', type=LOG_WARNING)
        else:
            return 3
    if len(buildtargets) != 3 and platform == "":
        log(f'There must be 3 successul build ({len(buildtargets)} for now)', type=LOG_ERROR)
        if force == "true":
            log(f'Process forced to continue (--force flag used)', type=LOG_WARNING)
        else:
            return 4
    log('OK', type=LOG_SUCCESS) 
    
    #download the builds from UCB
    if nodownload == "false":
        for build in buildtargets:
            #filter on the platforme we want (if platform is empty, it means that we must do it for all
            if build['platform'] == platform or platform == "":
                #store the data necessary for the next steps
                name = build['name']
                buildtargetid = build['buildtargetid']
                platformtemp = build['platform']
                buildospath = f'{buildpath}/{platformtemp}'
                
                if name == "" or buildtargetid == "" or platformtemp == "":
                    log(' Missing field', type=LOG_ERROR)
                    return 5
                
                if os.path.exists(f'{buildospath}/build.txt'):
                    os.remove(f'{buildospath}/build.txt')
                
                log(f' Preparing {platformtemp}') 
                if not "builds" in build:
                    log(' Missing builds field', type=LOG_ERROR)
                    return 6
                downloadlink = build['builds'][0]['links']['download_primary']['href']
                buildid =  build['builds'][0]['build']
                
                if build['builds'][0]['finished'] == "":
                    log(' The build seems to be a failed one', type=LOG_ERROR)
                    return 7
                finisheddate = datetime.strptime(build['builds'][0]['finished'], "%Y-%m-%dT%H:%M:%S.%fZ")
                currentdate = datetime.now()
                timediff = currentdate - finisheddate
                timediffinminute = int(timediff.total_seconds() / 60)
                log(f'  Continuing with build #{buildid} for {buildtargetid} finished {timediffinminute} minutes ago...') 
                if timediffinminute > 120:
                    log(' The build is too old', type=LOG_ERROR)
                    if force == "true":
                        log(f'Process forced to continue (--force flag used)', type=LOG_WARNING)
                    else:
                        return 8
                
                #store the buildtargetid in a txt file for the late cleaning process
                if os.path.exists(f'{buildpath}/{platformtemp}_build.txt'):
                    os.remove(f'{buildpath}/{platformtemp}_build.txt')
                write_in_file(f'{buildpath}/{platformtemp}_build.txt', f'{buildtargetid}::{buildid}')
                
                log(f'  Deleting old files in {buildospath}...', end="")
                if os.path.exists(f'/home/ubuntu/ucb{platformtemp}.zip'):
                    os.remove(f'/home/ubuntu/ucb{platformtemp}.zip')
                if os.path.exists(buildospath):
                    shutil.rmtree(buildospath, ignore_errors=True)
                log('OK', type=LOG_SUCCESS) 
                
                log('  Downloading the built zip file...', end="") 
                urllib.request.urlretrieve(downloadlink, f'/home/ubuntu/ucb{platformtemp}.zip')
                log('OK', type=LOG_SUCCESS) 
                
                log('  Extracting the zip file...', end="") 
                with ZipFile(f'/home/ubuntu/ucb{platformtemp}.zip', 'r') as zipObj:
                    zipObj.extractall(f'{buildospath}')
                    log('OK', type=LOG_SUCCESS)
        
                log('  Uploading copy to S3...', end="")
                ok = os.system(f'/home/ubuntu/uploadToS3.sh {STEAM_APPBRANCH} "ucb{platformtemp}.zip"')
                if ok != 0:
                    log(f'Executing the bash file /home/ubuntu/uploadToS3.sh (exitcode={ok})', type=LOG_ERROR)
                    return 9
                log('OK', type=LOG_SUCCESS)
                
                log('  Cleaning zip file...', end="")
                os.remove(f'/home/ubuntu/ucb{platformtemp}.zip')
                log('OK', type=LOG_SUCCESS)
                
                log('')
        
    
    if noupload == "false":
        #now prepare the steam files
        log('Preparing Steam files...', end="") 
        shutil.copyfile('/home/ubuntu/Steam/scripts/template_app_build.vdf', f'/home/ubuntu/Steam/scripts/app_build_{STEAM_APPID}.vdf')
        shutil.copyfile('/home/ubuntu/Steam/scripts/template_depot_build_standalonelinux64.vdf', f'/home/ubuntu/Steam/scripts/depot_build_standalonelinux64.vdf')
        shutil.copyfile('/home/ubuntu/Steam/scripts/template_depot_build_standaloneosxuniversal.vdf', f'/home/ubuntu/Steam/scripts/depot_build_standaloneosxuniversal.vdf')
        shutil.copyfile('/home/ubuntu/Steam/scripts/template_depot_build_standalonewindows64.vdf', f'/home/ubuntu/Steam/scripts/depot_build_standalonewindows64.vdf')
        
        replace_in_file(f'/home/ubuntu/Steam/scripts/app_build_{STEAM_APPID}.vdf', '%Version%', STEAM_APPVERSION)
        replace_in_file(f'/home/ubuntu/Steam/scripts/app_build_{STEAM_APPID}.vdf', '%Branch%', STEAM_APPBRANCH)
        replace_in_file(f'/home/ubuntu/Steam/scripts/app_build_{STEAM_APPID}.vdf', '%AppID%', STEAM_APPID)
        replace_in_file(f'/home/ubuntu/Steam/scripts/app_build_{STEAM_APPID}.vdf', '%AppDepotWindows%', STEAM_APPID_DEPOTWINDOWS)
        replace_in_file(f'/home/ubuntu/Steam/scripts/app_build_{STEAM_APPID}.vdf', '%AppDepotLinux%', STEAM_APPID_DEPOTLINUX)
        replace_in_file(f'/home/ubuntu/Steam/scripts/app_build_{STEAM_APPID}.vdf', '%AppDepotMacos%', STEAM_APPID_DEPOTMACOS)
        
        replace_in_file(f'/home/ubuntu/Steam/scripts/depot_build_standalonewindows64.vdf', '%AppDepotWindows%', STEAM_APPID_DEPOTWINDOWS)
        replace_in_file(f'/home/ubuntu/Steam/scripts/depot_build_standalonelinux64.vdf', '%AppDepotLinux%', STEAM_APPID_DEPOTLINUX)
        replace_in_file(f'/home/ubuntu/Steam/scripts/depot_build_standaloneosxuniversal.vdf', '%AppDepotMacos%', STEAM_APPID_DEPOTMACOS)
        
        if nolive == 'false' and STEAM_APPBRANCH != 'prod':
            replace_in_file(f'/home/ubuntu/Steam/scripts/app_build_{STEAM_APPID}.vdf', '%BranchLive%', STEAM_APPBRANCH)
        else:
            replace_in_file(f'/home/ubuntu/Steam/scripts/app_build_{STEAM_APPID}.vdf', '%BranchLive%', '')
        log('OK', type=LOG_SUCCESS) 
    
        log('Building Steam packages...', end="")
        #log(f'/home/ubuntu/Steam/steamcmd/steamcmd.sh +login "{STEAM_USER}" "{STEAM_PASSWORD}" +run_app_build /home/ubuntu/Steam/scripts/app_build_1121200.vdf +quit')
        ok = os.system(f'/home/ubuntu/Steam/steamcmd/steamcmd.sh +login "{STEAM_USER}" "{STEAM_PASSWORD}" +run_app_build /home/ubuntu/Steam/scripts/app_build_1121200.vdf +quit')
        if ok != 0:
            log(f'Executing the bash file /home/ubuntu/Steam/steamcmd/steamcmd.sh (exitcode={ok})', type=LOG_ERROR)
            return 9
        log('OK', type=LOG_SUCCESS)
    
    if noclean == "false":
        log('Cleaning successfully upload build in UCB...') 
        #let's remove the build successfully uploaded to steam from UCB
        directory = '/home/ubuntu/Steam/build'
        if sum(1 for e in os.scandir(directory)) != 6:
            log(f'Missing directory/file in {directory} (should have 6). Aborting...', type=LOG_ERROR)
            return 11
        
        for file in os.scandir(directory):
            if file.is_file():
                data = read_from_file(file.path)
                strsplit = data.split("::")
                buildtargetid = strsplit[0]
                build = strsplit[1]
                
                log(f' Deleting build #{build} for buildtarget {buildtargetid}...', end="")
                delete_build(buildtargetid, build)
                os.remove(file.path)
                log('OK', type=LOG_SUCCESS)

    log('All done!')
    return 0
    

if __name__ == "__main__":
    #create the log directory if it does not exists
    if not os.path.exists('/home/ubuntu/logs'):
        os.mkdir('/home/ubuntu/logs')
    #set the log file name with the current datetime
    DEBUG_FILE_NAME = f'/home/ubuntu/logs/{datetime.now().strftime("%Y%m%d_%H%M%S")}.html'
    #open the logfile for writing
    DEBUG_FILE = open(DEBUG_FILE_NAME, "wt")
    
    codeok = 0
    noshutdown = 'false'
    try:
        opts, args = getopt.getopt(sys.argv[1:],"hlndocsip:b:lv:u:a:",["help", "nolive", "nodependencies", "nodownload", "noupload", "noclean", "noshutdown", "force", "install", "platform=", "branch=", "version=", "steamuser=", "steampassword="])
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
            log('Shutting down computer...')
            os.system("sudo shutdown +1")
        
    log("--- Script execution time : %s seconds ---" % (time.time() - start_time))
    #close the logfile
    DEBUG_FILE.close()
    if codeok != 10 and codeok != 11:
        send_email(EMAIL_FROM, EMAIL_RECIPIENTS, 'Steam build result', read_from_file(DEBUG_FILE_NAME))
   