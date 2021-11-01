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
from typing import Dict, List
from zipfile import ZipFile

import boto3
import requests
import vdf
import yaml
from boto3.dynamodb.conditions import Key
from botocore.exceptions import ClientError
from colorama import Fore, Style

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

    def __lt__(self, other):
        if self.__class__ is other.__class__:
            return self.value < other.value

    def __gt__(self, other):
        if self.__class__ is other.__class__:
            return self.value > other.value

    def __str__(self):
        return str(self.name)


class UCBBuildStatus(Enum):
    SUCCESS = 1
    QUEUED = 2
    SENTTOBUILDER = 3
    STARTED = 4
    RESTARTED = 5
    FAILURE = 6
    CANCELED = 7
    UNKNOWN = 8

    def __str__(self):
        return str(self.name)


class Build:
    number: int
    build_target_id: str
    status: UCBBuildStatus
    date_finished: datetime
    download_link: str
    complete: bool
    platform: str
    UCB_object: dict

    def __init__(self, number: int, build_target_id: str, status: UCBBuildStatus, date_finished: str,
                 download_link: str, platform: str, UCB_object=None):
        self.number = number
        self.build_target_id = build_target_id
        self.status = status
        if date_finished == "":
            self.date_finished = datetime.min
        else:
            self.date_finished = datetime.strptime(date_finished, "%Y-%m-%dT%H:%M:%S.%fZ")
        self.download_link = download_link
        self.platform = platform
        if self.status == UCBBuildStatus.SUCCESS:
            self.complete = True
        else:
            self.complete = False
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
    concerned: bool
    stores: Dict[Store, Dict[str, BuildTarget]]

    def __init__(self, name: str, complete: bool = False, uploaded: bool = False, concerned: bool = False):
        self.name = name
        self.stores = dict()
        self.complete = complete
        self.uploaded = uploaded
        self.concerned = concerned

    def add_build_target(self, store: Store, build_target: BuildTarget):
        if store not in self.stores.keys():
            self.stores[store] = dict()

        self.stores[store][build_target.name] = build_target

    def contains_build_target(self, build_target_id: str) -> bool:
        found = False
        for store, build_targets in self.stores:
            if build_target_id in build_targets.keys():
                found = True

        return found

    def get_build_target(self, build_target_id: str) -> BuildTarget:
        build_target = None
        for store, build_targets in self.stores.items():
            if build_target_id in build_targets.keys():
                build_target = build_targets[build_target_id]

        return build_target

    def get_build_targets(self) -> List[BuildTarget]:
        build_targets_temp: List[BuildTarget] = list()
        for store, build_targets in self.stores.items():
            for build_target_name, build_target in build_targets.items():
                if build_target not in build_targets_temp:
                    build_targets_temp.append(build_target)

        return build_targets_temp

    def get_build_targets_for_store(self, store: Store) -> List[BuildTarget]:
        build_targets_temp: List[BuildTarget] = list()
        if store in self.stores:
            for build_target_name, build_target in self.stores[store].items():
                if build_target not in build_targets_temp:
                    build_targets_temp.append(build_target)

        return build_targets_temp

    def set_build_target_completion(self, build_target_id: str, complete: bool):
        for build_targets in self.stores.values():
            if build_target_id in build_targets.keys():
                build_targets[build_target_id].complete = complete

    def update_completion(self):
        if len(self.stores) == 0:
            # no stores means... not complete... master of the obvious!
            self.complete = False
        else:
            for store, build_targets in self.stores.items():
                if len(build_targets) == 0:
                    # no build_target means... not complete... master of the obvious chapter 2!
                    self.complete = False
                    break

                # if we reached this point, then we assume the package is completely built
                self.complete = True

        for store, build_targets in self.stores.items():
            for build_target_id, build_target in build_targets.items():
                # if one of the required build of the package is not complete, then the full package is incomplete
                if not build_target.complete:
                    self.complete = False

    def attach_build(self, build_target_id: str, build: Build):
        for store, build_targets in self.stores.items():
            if build_target_id in build_targets.keys():
                if build.status == UCBBuildStatus.SUCCESS:
                    self.concerned = True
                    if build_targets[build_target_id].build is not None:
                        if build_targets[build_target_id].build.number < build.number:
                            build_targets[build_target_id].build = build
                    else:
                        build_targets[build_target_id].build = build
                else:
                    if build_targets[build_target_id].build is None:
                        build_targets[build_target_id].build = build


# endregion

# region UNITY_LIBRARY
class UnityCloudBuild:
    org_id: str
    project_id: str
    api_key: str
    __builds__: List[Build]
    builds_categorized: Dict['str', List[Build]]

    def __init__(self, org_id: str, project_id: str, api_key: str):
        self.org_id = org_id
        self.project_id = project_id
        self.api_key = api_key

        self.builds_categorized = dict()
        self.builds_categorized['success']: List[Build] = list()
        self.builds_categorized['building']: List[Build] = list()
        self.builds_categorized['failure']: List[Build] = list()
        self.builds_categorized['canceled']: List[Build] = list()
        self.builds_categorized['unknown']: List[Build] = list()

    def update(self):
        """
        Update the buildtargets information from UnityCloudBuild
        """
        self.__builds__ = self.__get_all_builds__()

        self.builds_categorized['success'].clear()
        self.builds_categorized['building'].clear()
        self.builds_categorized['failure'].clear()
        self.builds_categorized['canceled'].clear()
        self.builds_categorized['unknown'].clear()

        for build in self.__builds__:
            if build.status == UCBBuildStatus.SUCCESS:
                self.builds_categorized['success'].append(build)
            elif build.status == UCBBuildStatus.QUEUED or build.status == UCBBuildStatus.SENTTOBUILDER or build.status == UCBBuildStatus.STARTED or build.status == UCBBuildStatus.RESTARTED:
                self.builds_categorized['building'].append(build)
            elif build.status == UCBBuildStatus.FAILURE:
                self.builds_categorized['failure'].append(build)
            elif build.status == UCBBuildStatus.CANCELED:
                self.builds_categorized['canceled'].append(build)
            else:
                self.builds_categorized['unknown'].append(build)

    def get_builds(self, platform: str = "") -> List[Build]:
        if self.__builds__ is None:
            self.update()

        data_temp: List[Build] = list()
        # filter on platform
        if platform != "":
            for build in self.__builds__:
                if build.platform != platform:
                    # the platform is different: remove the build from the result
                    data_temp.append(build)
                    continue
                else:
                    log(f"The platform was not detected", log_type=LOG_WARNING)
                    data_temp.append(build)
                    continue

        return data_temp

    def __api_url__(self) -> str:
        return 'https://build-api.cloud.unity3d.com/api/v1/orgs/{}/projects/{}'.format(self.org_id,
                                                                                       self.project_id)

    def __headers__(self) -> dict:
        return {'Authorization': 'Basic {}'.format(self.api_key)}

    def create_new_build_target(self, data, branch, user):
        name_limit = 64 - 17 - len(user)
        name = re.sub("[^0-9a-zA-Z]+", "-", branch)[0:name_limit]

        data['name'] = 'Autobuild of {} by {}'.format(name, user)
        data['settings']['scm']['branch'] = branch

        url = '{}/buildtargets'.format(self.__api_url__())
        response = requests.post(url, headers=self.__headers__(), json=data)

        if not response.ok:
            logging.error("Creating build target " + data['name'] + " failed", response.text)

        info = response.json()
        return info['buildtargetid'], data['name']

    def delete_build_target(self, build_target_id: str):
        url = '{}/buildtargets/{}'.format(self.__api_url__(), build_target_id)
        requests.delete(url, headers=self.__headers__())

    def start_build(self, build_target_id: str):
        url = '{}/buildtargets/{}/builds'.format(self.__api_url__(), build_target_id)
        data = {'clean': True}
        requests.post(url, headers=self.__headers__(), json=data)

    def create_build_url(self, build_target_id: str, build_number: int) -> str:
        return 'https://developer.cloud.unity3d.com/build/orgs/{}/projects/{}/buildtargets/{}/builds/{}/log/compact/'.format(
            self.org_id, self.project_id, build_target_id, str(build_number)
        )

    def get_last_builds(self, build_target: str = "", platform: str = "") -> List[Build]:
        url = '{}/buildtargets?include_last_success=true'.format(self.__api_url__())
        response = requests.get(url, headers=self.__headers__())

        data_temp = []

        if not response.ok:
            log(f"Getting build template failed: {response.text}", log_type=LOG_ERROR)
            return data_temp

        data = response.json()
        data_temp = copy.deepcopy(data)
        # let's filter the result on the requested branch only
        for i in reversed(range(0, len(data))):
            build = data[i]

            # identify if the build is successful
            if "builds" not in build:
                # log(f"Missing builds field for {build["buildtargetid"]}", type=LOG_ERROR)
                data_temp.pop(i)
                continue

            # filter on build target
            if build_target != "":
                if build['buildtargetid'] is None:
                    if build['buildtargetid'] != build_target:
                        data_temp.pop(i)
                        continue
                else:
                    log(f"The buildtargetid was not detected", log_type=LOG_ERROR)
                    data_temp.pop(i)
                    continue

            # filter on platform
            if platform != "":
                if not build['platform'] is None:
                    if build['platform'] != platform:
                        # the platform is different: remove the build from the result
                        data_temp.pop(i)
                        continue
                else:
                    log(f"The platform was not detected", log_type=LOG_ERROR)
                    data_temp.pop(i)
                    continue

        final_data: List[Build] = list()
        for build in data_temp:
            build_primary = ''
            build_status = UCBBuildStatus.UNKNOWN
            build_finished = ''

            if 'buildStatus' in build:
                if build['buildStatus'] == 'success':
                    build_status = UCBBuildStatus.SUCCESS
                elif build['buildStatus'] == 'started':
                    build_status = UCBBuildStatus.STARTED
                elif build['buildStatus'] == 'queued':
                    build_status = UCBBuildStatus.QUEUED
                elif build['buildStatus'] == 'failure':
                    build_status = UCBBuildStatus.FAILURE
                elif build['buildStatus'] == 'canceled':
                    build_status = UCBBuildStatus.CANCELED
                elif build['buildStatus'] == 'restarted':
                    build_status = UCBBuildStatus.RESTARTED
                elif build['buildStatus'] == 'sentToBuilder':
                    build_status = UCBBuildStatus.SENTTOBUILDER

            if 'download_primary' in build['links']:
                build_primary = build['links']['download_primary']['href']

            if 'finished' in build:
                build_finished = build['finished']

            if 'build' not in build:
                continue

            if 'buildtargetid' not in build:
                continue

            if 'platform' not in build:
                continue

            build_obj = Build(number=build['build'], build_target_id=build['buildtargetid'], status=build_status,
                              date_finished=build_finished, download_link=build_primary, platform=build['platform'],
                              UCB_object=build)

            final_data.append(build_obj)

        final_data.sort(key=lambda item: item.number)

        return final_data

    def __get_all_builds__(self, build_target: str = "") -> List[Build]:
        url = '{}/buildtargets/_all/builds'.format(self.__api_url__())
        response = requests.get(url, headers=self.__headers__())

        data_temp = []

        if not response.ok:
            log(f"Getting build template failed: {response.text}", log_type=LOG_ERROR)
            return data_temp

        data = response.json()
        data_temp = copy.deepcopy(data)
        # let's filter the result on the requested branch only
        for i in reversed(range(0, len(data))):
            build = data[i]

            # identify if the build is successful
            if "build" not in build:
                # log(f"Missing build field for {build["build"]}", type=LOG_ERROR)
                data_temp.pop(i)
                continue

            # filter on build target
            if build_target != "":
                if build['buildtargetid'] is None:
                    if build['buildtargetid'] != build_target:
                        data_temp.pop(i)
                        continue
                else:
                    log(f"The buildtargetid was not detected", log_type=LOG_ERROR)
                    data_temp.pop(i)
                    continue

        final_data: List[Build] = list()
        for build in data_temp:
            build_primary = ''
            build_status = UCBBuildStatus.UNKNOWN
            build_finished = ''

            if build['buildStatus'] == 'success':
                build_status = UCBBuildStatus.SUCCESS
            elif build['buildStatus'] == 'started':
                build_status = UCBBuildStatus.STARTED
            elif build['buildStatus'] == 'queued':
                build_status = UCBBuildStatus.QUEUED
            elif build['buildStatus'] == 'failure':
                build_status = UCBBuildStatus.FAILURE
            elif build['buildStatus'] == 'canceled':
                build_status = UCBBuildStatus.CANCELED
            elif build['buildStatus'] == 'restarted':
                build_status = UCBBuildStatus.RESTARTED
            elif build['buildStatus'] == 'sentToBuilder':
                build_status = UCBBuildStatus.SENTTOBUILDER

            if 'download_primary' in build['links']:
                build_primary = build['links']['download_primary']['href']

            if 'finished' in build:
                build_finished = build['finished']

            build_obj = Build(number=build['build'], build_target_id=build['buildtargetid'], status=build_status,
                              date_finished=build_finished, download_link=build_primary, platform=build['platform'],
                              UCB_object=build)

            final_data.append(build_obj)

        final_data.sort(key=lambda item: item.number)

        return final_data

    def delete_build(self, build_target_id: str, build: int) -> bool:
        deleted = True
        url = '{}/artifacts/delete'.format(self.__api_url__())

        data = {'builds': [{"buildtargetid": build_target_id, "build": build}]}

        response = requests.post(url, headers=self.__headers__(), json=data)

        if not response.ok:
            deleted = False
            log(f"Deleting build target failed: {response.text}", log_type=LOG_ERROR)

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
    # override the input file with the resulting data
    fin.write(data)
    # close the file
    fin.close()


def write_in_file(file, data):
    # open the input file in write mode
    fin = open(file, "wt")
    # override the input file with the resulting data
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
def send_email(sender, recipients, title, message, quiet=False):
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
        log(e.response['Error']['Message'], log_type=LOG_ERROR)
        return 461
    else:
        if not quiet:
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
        client.download_file(
            Filename=destination,
            Bucket=bucket,
            Key=file,
        )
        return 0
    # Display an error if something goes wrong.
    except ClientError as e:
        log(e.response['Error']['Message'], log_type=LOG_ERROR)
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
            client.download_file(
                Filename=target,
                Bucket=bucket_name,
                Key=obj.key,
            )
        return 0
    # Display an error if something goes wrong.
    except ClientError as e:
        log(e.response['Error']['Message'], log_type=LOG_ERROR)
        return 440


def s3_upload_file(filetoupload, bucket_name, destination):
    global CFG
    client = boto3.client("s3", region_name=CFG['aws']['region'])
    try:
        client.put_object(
            Bucket=bucket_name,
            Key=destination,
            Body=open(filetoupload, 'rb')
        )

        return 0
    # Display an error if something goes wrong.
    except ClientError as e:
        log(e.response['Error']['Message'], log_type=LOG_ERROR)
        return 450


def s3_delete_file(bucket_name, file_to_delete):
    global CFG
    client = boto3.client("s3", region_name=CFG['aws']['region'])
    try:
        client.put_object(
            Bucket=bucket_name,
            Key=file_to_delete
        )

        return 0
    # Display an error if something goes wrong.
    except ClientError as e:
        log(e.response['Error']['Message'], log_type=LOG_ERROR)
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


def get_packages(dynamodb=None) -> Dict[str, Package]:
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
                        package = Package(name=package_name, complete=False)
                        packages[package_name] = package

                    # region BuildTarget creation
                    build_target_obj = BuildTarget(name=build_target['id'], complete=False)
                    for parameter, value in build_target['steam'].items():
                        if parameter != 'package':
                            build_target_obj.parameters[parameter] = value
                    # endregion

                    packages[package_name].add_build_target(Store.STEAM, build_target_obj)

            if 'butler' in build_target:
                if 'package' in build_target['butler']:
                    package_name = build_target['butler']['package']
                    if package_name not in packages:
                        package = Package(name=package_name, complete=False)
                        packages[package_name] = package

                    # region BuildTarget creation
                    build_target_obj = BuildTarget(name=build_target['id'], complete=False)
                    for parameter, value in build_target['butler'].items():
                        if parameter != 'package':
                            build_target_obj.parameters[parameter] = value
                    # endregion

                    packages[package_name].add_build_target(Store.ITCH, build_target_obj)
    except ClientError as e:
        print(e.response['Error']['Message'])
    else:
        for package_name, package in packages.items():
            packages[package_name].stores = dict(sorted(package.stores.items()))
        return packages


# endregion

# region HELPER LIBRARY
def log(message: str, end: str = "\r\n", no_date: bool = False, log_type=LOG_INFO, no_prefix: bool = False):
    global DEBUG_FILE

    str_print = ""
    str_file = ""
    str_date = datetime.now().strftime("%Y/%m/%d %H:%M:%S")

    if not no_date:
        str_print = str_date + " - "
        str_file = str_date + " - "

    if log_type == LOG_ERROR:
        str_print = str_print + f"{Fore.RED}"
        if not no_prefix:
            str_print = str_print + "ERROR: "
        str_file = str_file + "<font color='red'>"
        if not no_prefix:
            str_file = str_file + "ERROR: "
    elif log_type == LOG_WARNING:
        str_print = str_print + f"{Fore.YELLOW}"
        if not no_prefix:
            str_print = str_print + "WARNING: "
        str_file = str_file + "<font color='yellow'>"
        if not no_prefix:
            str_file = str_file + "WARNING: "
    elif log_type == LOG_SUCCESS:
        str_print = str_print + f"{Fore.GREEN}"
        str_file = str_file + "<font color='green'>"

    str_print = str_print + message
    str_file = str_file + message

    if log_type == LOG_ERROR or log_type == LOG_WARNING or log_type == LOG_SUCCESS:
        str_print = str_print + f"{Style.RESET_ALL}"
        str_file = str_file + "</font>"

    if end == "":
        print(str_print, end="")
    else:
        print(str_print)
    if not DEBUG_FILE.closed:
        if end == "":
            DEBUG_FILE.write(str_file)
            DEBUG_FILE.flush()
        else:
            DEBUG_FILE.write(str_file + '</br>' + end)
            DEBUG_FILE.flush()


def print_help():
    print(
        f"UCB-steam.py --platform=(standalonelinux64, standaloneosxuniversal, standalonewindows64) [--nolive] [--force] [--version=<version>] [--install] [--nodownload] [--noupload] [--noclean] [--noshutdown] [--noemail] [--simulate] [--showconfig | --showdiag] [--steamuser=<steamuser>] [--steampassword=<steampassword>]")


def print_config(packages: Dict[str, Package], with_diag: bool = False):
    for package_name, package in packages.items():
        log(f'name: {package_name}', no_date=True)

        if with_diag:
            log(f'  concerned: ', no_date=True, end="")
            if package.concerned:
                log('YES', no_date=True, log_type=LOG_SUCCESS)
            else:
                log('NO', no_date=True, no_prefix=True, log_type=LOG_WARNING)

            log(f'  complete: ', no_date=True, end="")
            if package.complete:
                log('YES', no_date=True, log_type=LOG_SUCCESS)
            else:
                if package.concerned:
                    log('NO', no_date=True, no_prefix=True, log_type=LOG_ERROR)
                else:
                    log('NO (not concerned)', no_date=True, log_type=LOG_WARNING, no_prefix=True)

        for store, build_targets in package.stores.items():
            log(f'  store: {store}', no_date=True)
            for build_target_id, build_target in build_targets.items():
                log(f'    buildtarget: {build_target_id}', no_date=True)
                if with_diag:
                    log(f'      complete: ', no_date=True, end="")
                    if build_target.complete:
                        log('YES', no_date=True, log_type=LOG_SUCCESS)
                    else:
                        if package.concerned:
                            log('NO', no_date=True, no_prefix=True, log_type=LOG_ERROR)
                        else:
                            log('NO (not concerned)', no_date=True, log_type=LOG_WARNING, no_prefix=True)

                for key, value in build_target.parameters.items():
                    log(f'      {key}: {value}', no_date=True)

                if with_diag:
                    if build_target.build:
                        log(f'      builds: #{build_target.build.number} ({build_target.build.status})', no_date=True)
                        log(f'        complete: ', no_date=True, end="")
                        if build_target.build.complete:
                            log('YES', no_date=True, log_type=LOG_SUCCESS)
                        else:
                            if package.concerned:
                                log('NO', no_date=True, no_prefix=True, log_type=LOG_ERROR)
                            else:
                                log('NO (not concerned)', no_date=True, log_type=LOG_WARNING, no_prefix=True)

        log('', no_date=True)


# endregion

def main(argv):
    global DEBUG_FILE_NAME

    global CFG

    log("Settings environment variables...", end="")
    log("OK", log_type=LOG_SUCCESS, no_date=True)

    steam_appversion = ""

    platform = ""
    no_download = False
    no_upload = False
    no_clean = False
    force = False
    install = False
    show_config = False
    show_diag = False
    no_live = False
    simulate = False
    try:
        options, arguments = getopt.getopt(argv, "hldocsfip:lv:t:u:a:",
                                           ["help", "nolive", "nodownload", "noupload", "noclean", "noshutdown",
                                            "noemail",
                                            "force", "install", "simulate", "showconfig", "showdiag", "platform=",
                                            "version=",
                                            "steamuser=",
                                            "steampassword="])
    except getopt.GetoptError:
        return 10

    for option, argument in options:
        if option in ("-h", "--help"):
            print_help()
            return 10
        elif option in ("-p", "--platform"):
            if argument != "standalonelinux64" and argument != "standaloneosxuniversal" and argument != "standalonewindows64":
                print_help()
                return 10
            platform = argument
        elif option in ("-i", "--install"):
            no_download = True
            no_upload = True
            no_clean = True
            install = True
        elif option in ("-d", "--nodownload"):
            no_download = True
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
            CFG['steam']['user'] = argument
        elif option in ("-a", "--steampassword"):
            CFG['steam']['password'] = argument

    # region STEAM AND BUTLER VARIABLES
    steam_dir_path = f'{CFG["basepath"]}/Steam'
    steam_build_path = f'{steam_dir_path}/build'
    steam_scripts_path = f'{steam_dir_path}/scripts'
    steam_exe_path = f'{steam_dir_path}/steamcmd/steamcmd.sh'
    butler_dir_path = f'{CFG["basepath"]}/Butler'
    butler_exe_path = ''
    if sys.platform.startswith('linux'):
        butler_exe_path = f'{butler_dir_path}/butler'
    elif sys.platform.startswith('win32'):
        butler_exe_path = f'{butler_dir_path}/butler.exe'
    butler_config_dir_path = f'{CFG["homepath"]}/.config/ich'
    butler_config_file_path = f'{butler_config_dir_path}/butler_creds'
    # endregion

    # region INSTALL
    # install all the dependencies and test them
    if install:
        log("Updating apt sources...", end="")
        if not simulate:
            if sys.platform.startswith('linux'):
                ok = os.system("sudo apt-get update -qq -y > /dev/null 1")
                if ok > 0:
                    log("Dependencies installation failed", log_type=LOG_ERROR, no_date=True)
                    return 210
                log("OK", log_type=LOG_SUCCESS, no_date=True)
            else:
                log("OS is not Linux", log_type=LOG_SUCCESS, no_date=True)
        else:
            log("Skipped", log_type=LOG_SUCCESS, no_date=True)

        log("Installing dependencies...", end="")
        if not simulate:
            if sys.platform.startswith('linux'):
                ok = os.system("sudo apt-get install -qq -y mc python3-pip git lib32gcc1 python3-requests > /dev/null")
                if ok > 0:
                    log("Dependencies installation failed", log_type=LOG_ERROR, no_date=True)
                    return 211
                log("OK", log_type=LOG_SUCCESS, no_date=True)
            elif sys.platform.startswith('win32'):
                ok = os.system("python.exe -m pip install --upgrade pip --no-warn-script-location 1> nul")
                if ok > 0:
                    log("Dependencies installation failed", log_type=LOG_ERROR, no_date=True)
                    return 211
                log("OK", log_type=LOG_SUCCESS, no_date=True)
        else:
            log("Skipped", log_type=LOG_SUCCESS, no_date=True)

        log("Installing AWS cli...", end="")
        if not simulate:
            if sys.platform.startswith('linux'):
                ok = os.system('curl "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o "' + CFG[
                    'basepath'] + '/awscliv2.zip" --silent')
                if ok > 0:
                    log("Dependencies installation failed", log_type=LOG_ERROR, no_date=True)
                    return 212
                ok = os.system('unzip -oq ' + CFG['basepath'] + '/awscliv2.zip -d ' + CFG['basepath'])
                if ok > 0:
                    log("Dependencies installation failed", log_type=LOG_ERROR, no_date=True)
                    return 213
                ok = os.system('rm ' + CFG['basepath'] + '/awscliv2.zip')
                if ok > 0:
                    log("Dependencies installation failed", log_type=LOG_ERROR, no_date=True)
                    return 214
                ok = os.system('sudo ' + CFG['basepath'] + '/aws/install --update')
                if ok > 0:
                    log("Dependencies installation failed", log_type=LOG_ERROR, no_date=True)
                    return 215
                log("OK", log_type=LOG_SUCCESS, no_date=True)
            else:
                log("OS is not Linux", log_type=LOG_SUCCESS, no_date=True)
        else:
            log("Skipped", log_type=LOG_SUCCESS, no_date=True)

        log("Installing python dependencies...", end="")
        if not simulate:
            if sys.platform.startswith('linux'):
                ok = os.system(f"sudo pip3 install -r {CFG['basepath']}/requirements.txt > /dev/null")
                if ok > 0:
                    log("Dependencies installation failed", log_type=LOG_ERROR, no_date=True)
                    return 216
                log("OK", log_type=LOG_SUCCESS, no_date=True)
            elif sys.platform.startswith('win32'):
                cmd = f"python3 -m pip install -r {CFG['basepath']}\\requirements.txt 1> nul"
                ok = os.system(cmd)
                if ok > 0:
                    log("Dependencies installation failed", log_type=LOG_ERROR, no_date=True)
                    return 216
                log("OK", log_type=LOG_SUCCESS, no_date=True)
            else:
                log("OS is neither Windows or Linux", log_type=LOG_ERROR, no_date=True)
        else:
            log("Skipped", log_type=LOG_SUCCESS, no_date=True)

        log("Configuring AWS credentials...", end="")
        if not simulate:
            if not os.path.exists(CFG['homepath'] + '/.aws'):
                os.mkdir(CFG['homepath'] + '/.aws')

            write_in_file(CFG['homepath'] + '/.aws/config',
                          '[default]\r\nregion=' + CFG['aws']['region'] + '\r\noutput=json\r\naws_access_key_id=' +
                          CFG['aws']['accesskey'] + '\r\naws_secret_access_key=' + CFG['aws']['secretkey'])

            log("OK", log_type=LOG_SUCCESS, no_date=True)
        else:
            log("Skipped", log_type=LOG_SUCCESS, no_date=True)

        log("Testing AWS connection...", end="")
        ok = os.system('echo "Success" > ' + CFG['basepath'] + '/test_successful.txt')
        if ok != 0:
            log("Creating temp file for connection test to AWS", log_type=LOG_ERROR, no_date=True)
            return 300
        ok = s3_upload_file(CFG['basepath'] + '/test_successful.txt', CFG['aws']['s3bucket'],
                            'UCB/steam-parameters/test_successful.txt')
        if ok != 0:
            log("Error uploading file to AWS UCB/steam-parameters. Check the IAM permissions", log_type=LOG_ERROR,
                no_date=True)
            return 301
        ok = s3_delete_file(CFG['aws']['s3bucket'], 'UCB/steam-parameters/test_successful.txt')
        if ok != 0:
            log("Error deleting file from AWS UCB/steam-parameters. Check the IAM permissions", log_type=LOG_ERROR,
                no_date=True)
            return 302
        ok = s3_upload_file(CFG['basepath'] + '/test_successful.txt', CFG['aws']['s3bucket'],
                            'UCB/unity-builds/test_successful.txt')
        if ok != 0:
            log("Error uploading file to AWS UCB/unity-builds. Check the IAM permissions", log_type=LOG_ERROR,
                no_date=True)
            return 303
        ok = s3_delete_file(CFG['aws']['s3bucket'], 'UCB/unity-builds/test_successful.txt')
        if ok != 0:
            log("Error deleting file from AWS UCB/unity-builds. Check the IAM permissions", log_type=LOG_ERROR,
                no_date=True)
            return 302
        os.remove(CFG['basepath'] + '/test_successful.txt')
        ok = os.path.exists(CFG['basepath'] + '/test_successful.txt')
        if ok != 0:
            log("Error deleting after connecting to AWS", log_type=LOG_ERROR, no_date=True)
            return 304
        log("OK", log_type=LOG_SUCCESS, no_date=True)

        log("Installing UCB-steam startup script...", end="")
        if not simulate:
            if sys.platform.startswith('linux'):
                shutil.copyfile(CFG['basepath'] + '/UCB-steam-startup-script.example',
                                CFG['basepath'] + '/UCB-steam-startup-script')
                replace_in_file(CFG['basepath'] + '/UCB-steam-startup-script', '%basepath%', CFG['basepath'])
                ok = os.system(
                    'sudo mv ' + CFG[
                        'basepath'] + '/UCB-steam-startup-script /etc/init.d/UCB-steam-startup-script > /dev/null')
                if ok != 0:
                    log("Error copying UCB-steam startup script file to /etc/init.d", log_type=LOG_ERROR, no_date=True)
                    return 310
                ok = os.system(
                    'sudo chown root:root /etc/init.d/UCB-steam-startup-script ; sudo chmod 755 /etc/init.d/UCB-steam-startup-script ; sudo systemctl daemon-reload > /dev/null')
                if ok > 0:
                    log("Error setting permission to UCB-steam startup script file", log_type=LOG_ERROR, no_date=True)
                    return 311
                log("OK", log_type=LOG_SUCCESS, no_date=True)
            else:
                log("OS is not Linux", log_type=LOG_SUCCESS, no_date=True)
        else:
            log("Skipped", log_type=LOG_SUCCESS, no_date=True)

        log("Creating folder structure for Steamworks...", end="")
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
            log("OK", log_type=LOG_SUCCESS, no_date=True)
        else:
            log("Skipped", log_type=LOG_SUCCESS, no_date=True)

        log("Testing UCB connection...", end="")
        UCB: UnityCloudBuild = UnityCloudBuild(org_id=CFG['unity']['org_id'], project_id=CFG['unity']['project_id'],
                                                   api_key=CFG['unity']['api_key'])
        UCB_builds_test = UCB.get_last_builds(platform=platform)
        if UCB_builds_test is None:
            log("Error connecting to UCB", log_type=LOG_ERROR, no_date=True)
            return 21
        log("OK", log_type=LOG_SUCCESS, no_date=True)

        log("Downloading Steamworks SDK...", end="")
        if not simulate:
            if not os.path.exists(f"{steam_dir_path}/steamcmd/linux32/steamcmd"):
                ok = s3_download_directory("UCB/steam-sdk", CFG['aws']['s3bucket'], f"{CFG['basepath']}/steam-sdk")
                if ok != 0:
                    log("Error getting files from S3", log_type=LOG_ERROR, no_date=True)
                    return 22

                shutil.copytree(f"{CFG['basepath']}/steam-sdk/builder_linux", f"{steam_dir_path}/steamcmd",
                                dirs_exist_ok=True)
                st = os.stat(steam_exe_path)
                os.chmod(steam_exe_path, st.st_mode | stat.S_IEXEC)
                st = os.stat(f"{steam_dir_path}/steamcmd/linux32/steamcmd")
                os.chmod(f"{steam_dir_path}/steamcmd/linux32/steamcmd", st.st_mode | stat.S_IEXEC)
                shutil.rmtree(f"{CFG['basepath']}/steam-sdk")
                log("OK", log_type=LOG_SUCCESS, no_date=True)
            else:
                log("OK (dependencie already met)", log_type=LOG_SUCCESS, no_date=True)
        else:
            log("Skipped", log_type=LOG_SUCCESS, no_date=True)

        log("Testing Steam connection...", end="")
        ok = os.system(f'''{steam_exe_path} +login "{CFG['steam']['user']}" "{CFG['steam']['password']}" +quit''')
        if ok != 0:
            log("Error connecting to Steam", log_type=LOG_ERROR, no_date=True)
            return 23
        log("OK", log_type=LOG_SUCCESS, no_date=True)

        log("Creating folder structure for Butler...", end="")
        if not simulate:
            if not os.path.exists(f'{CFG["homepath"]}/.config'):
                os.mkdir(f'{CFG["homepath"]}/.config')
            if not os.path.exists(butler_config_dir_path):
                os.mkdir(butler_config_dir_path)

            if not os.path.exists(butler_dir_path):
                os.mkdir(butler_dir_path)

            log("OK", log_type=LOG_SUCCESS, no_date=True)
        else:
            log("Skipped", log_type=LOG_SUCCESS, no_date=True)

        log("Downloading Butler...", end="")
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
                    log("Error downloading Butler", log_type=LOG_ERROR, no_date=True)
                    return 24

                unzipped = 1
                with ZipFile(zip_path, "r") as zipObj:
                    zipObj.extractall(butler_dir_path)
                    unzipped = 0

                if unzipped != 0:
                    log("Error unzipping Butler", log_type=LOG_ERROR, no_date=True)
                    return 23

                st = os.stat(butler_exe_path)
                os.chmod(butler_exe_path, st.st_mode | stat.S_IEXEC)

                log("OK", log_type=LOG_SUCCESS, no_date=True)
            else:
                log("OK (dependencie already met)", log_type=LOG_SUCCESS, no_date=True)
        else:
            log("Skipped", log_type=LOG_SUCCESS, no_date=True)

        log("Setting up Butler...", end="")
        if not simulate:
            write_in_file(butler_config_file_path, CFG['butler']['apikey'])
            if not os.path.exists(butler_config_file_path):
                log("Error setting up Butler", log_type=LOG_ERROR, no_date=True)
                return 25
        log("OK", log_type=LOG_SUCCESS, no_date=True)

        log("Testing Butler connection...", end="")
        cmd = f'{butler_exe_path} status {CFG["butler"]["org"]}/{CFG["butler"]["project"]} 1> nul'
        ok = os.system(cmd)
        if ok != 0:
            log("Error connecting to Butler", log_type=LOG_ERROR, no_date=True)
            return 23
        log("OK", log_type=LOG_SUCCESS, no_date=True)

        log("Testing email notification...", end="")
        str_log = '<b>Result of the UCB-steam script installation:</b>\r\n</br>\r\n</br>'
        str_log = str_log + read_from_file(DEBUG_FILE_NAME)
        str_log = str_log + '\r\n</br>\r\n</br><font color="GREEN">Everything is set up correctly. Congratulations !</font>'
        ok = send_email(CFG['email']['from'], CFG['email']['recipients'], "Steam build notification test", str_log,
                        True)
        if ok != 0:
            log("Error sending email", log_type=LOG_ERROR, no_date=True)
            return 35
        log("OK", log_type=LOG_SUCCESS, no_date=True)

        log("Everything is set up correctly. Congratulations !", log_type=LOG_SUCCESS)

        return 0
    # endregion

    # region PACKAGES CONFIG
    log(f"Retrieving configuration from DynamoDB...", end="")
    CFG_packages = get_packages()
    log("OK", no_date=True, log_type=LOG_SUCCESS)
    # endregion

    # region SHOW CONFIG
    if show_config:
        log(f"Displaying configuration...")
        log('', no_date=True)

        print_config(packages=CFG_packages)

        return 0
    # endregion

    # region UCB builds information query
    # Get all the successful builds from Unity Cloud Build
    build_filter = ""
    if platform != "":
        build_filter = f"(Filtering on platform:{platform})"
    if build_filter != "":
        log(f"Retrieving all the builds information from UCB {build_filter}...", end="")
    else:
        log(f"Retrieving all the builds information from UCB...", end="")

    UCB: UnityCloudBuild = UnityCloudBuild(org_id=CFG['unity']['org_id'], project_id=CFG['unity']['project_id'],
                                               api_key=CFG['unity']['api_key'])

    UCB_all_builds: List[Build] = UCB.get_builds(platform=platform)
    if len(UCB_all_builds) == 0:
        if force:
            log("No build available in UCB but process forced to continue (--force flag used)", log_type=LOG_WARNING,
                no_date=True)
        elif show_diag:
            log("No build available in UCB but process forced to continue (--showdiag flag used)",
                log_type=LOG_WARNING,
                no_date=True)
        else:
            log("No build available in UCB", log_type=LOG_SUCCESS, no_date=True)
            return 3
    else:
        log("OK", log_type=LOG_SUCCESS, no_date=True)

    # filter on successful builds only
    log(f" {len(UCB.builds_categorized['success'])} builds are successful and waiting for processing",
        log_type=LOG_SUCCESS)
    if len(UCB.builds_categorized['building']) > 0:
        log(f" {len(UCB.builds_categorized['building'])} builds are building", log_type=LOG_WARNING, no_prefix=True)
    if len(UCB.builds_categorized['failure']) > 0:
        log(f" {len(UCB.builds_categorized['failure'])} builds are failed", log_type=LOG_ERROR, no_prefix=True)
    if len(UCB.builds_categorized['canceled']) > 0:
        log(f" {len(UCB.builds_categorized['canceled'])} builds are canceled", log_type=LOG_ERROR, no_prefix=True)
    if len(UCB.builds_categorized['unknown']) > 0:
        log(f" {len(UCB.builds_categorized['unknown'])} builds are in a unknown state", log_type=LOG_WARNING,
            no_prefix=True)
    # endregion

    # region PACKAGE COMPLETION CHECK
    # identify completed builds
    log(f"Compiling UCB data with configuration...", end="")
    for build in UCB_all_builds:
        for package_name, package in CFG_packages.items():
            package.attach_build(build_target_id=build.build_target_id, build=build)
            if build.status == UCBBuildStatus.SUCCESS:
                package.set_build_target_completion(build_target_id=build.build_target_id, complete=True)

    # identify the full completion of a package (based on the configuration)
    for package_name, package in CFG_packages.items():
        package.update_completion()

    log("OK", no_date=True, log_type=LOG_SUCCESS)
    # endregion

    # region SHOW DIAG
    if show_diag:
        log(f"Displaying diagnostics...")
        log('', no_date=True)

        print_config(packages=CFG_packages, with_diag=True)

        return 0
    # endregion

    can_continue = False
    for package_name, package in CFG_packages.items():
        if package.complete:
            can_continue = True

    log(" One or more packages complete...", end="")
    if can_continue:
        log("OK", no_date=True, log_type=LOG_SUCCESS)
    elif force:
        log(f"Process forced to continue (--force flag used)", no_date=True, log_type=LOG_WARNING)
    else:
        log("At least one package must be complete to proceed to the next step", no_date=True, log_type=LOG_ERROR)
        return 4

    # download the builds from UCB
    if not no_download:
        log("--------------------------------------------------------------------------", no_date=True)
        log("Downloading build from UCB...")
        for package_name, package in CFG_packages.items():
            if package.complete:
                build_targets = package.get_build_targets()
                for build_target in build_targets:
                    # store the data necessary for the next steps
                    build_os_path = steam_build_path + '/' + build_target.name

                    if build_target.build is None:
                        log(" Missing build object", log_type=LOG_ERROR)
                        return 5

                    if not simulate:
                        if os.path.exists(f"{build_os_path}/{build_target.name}_build.txt"):
                            os.remove(f"{build_os_path}/{build_target.name}_build.txt")

                    log(f" Preparing {build_target.name}")
                    if build_target.build.number == "":
                        log(" Missing builds field", log_type=LOG_ERROR, no_date=True)
                        return 6

                    if build_target.build.date_finished == datetime.min:
                        log(" The build seems to be a failed one", log_type=LOG_ERROR, no_date=True)
                        return 7

                    current_date = datetime.now()
                    time_diff = current_date - build_target.build.date_finished
                    time_diff_in_minute = int(time_diff.total_seconds() / 60)
                    log(f"  Continuing with build #{build_target.build.number} for {build_target.name} finished {time_diff_in_minute} minutes ago...",
                        end="")
                    if time_diff_in_minute > CFG['unity']['build_max_age']:
                        if force:
                            log(" Process forced to continue (--force flag used)", log_type=LOG_WARNING, no_date=True)
                        else:
                            log(f" The build is too old (max {str(CFG['unity']['build_max_age'])} min)",
                                log_type=LOG_ERROR,
                                no_date=True)
                            return 8
                    else:
                        log(f"OK", log_type=LOG_SUCCESS, no_date=True)

                    # store the buildtargetid in a txt file for the late cleaning process
                    if not simulate:
                        if os.path.exists(f"{steam_build_path}/{build_target.name}_build.txt"):
                            os.remove(f"{steam_build_path}/{build_target.name}_build.txt")
                        write_in_file(f"{steam_build_path}/{build_target.name}_build.txt",
                                      f"{build_target.name}::{build_target.build.number}")

                    zipfile = f"{CFG['basepath']}/ucb{build_target.name}.zip"

                    log(f"  Deleting old files in {build_os_path}...", end="")
                    if not simulate:
                        if os.path.exists(zipfile):
                            os.remove(zipfile)
                        if os.path.exists(build_os_path):
                            shutil.rmtree(build_os_path, ignore_errors=True)
                    log("OK", log_type=LOG_SUCCESS, no_date=True)

                    log(f'  Downloading the built zip file {zipfile}...', end="")
                    if not simulate:
                        urllib.request.urlretrieve(build_target.build.download_link, zipfile)
                    log("OK", log_type=LOG_SUCCESS, no_date=True)

                    log(f'  Extracting the zip file in {build_os_path}...', end="")
                    if not simulate:
                        unzipped = 1
                        with ZipFile(zipfile, "r") as zipObj:
                            zipObj.extractall(build_os_path)
                            unzipped = 0
                            log("OK", log_type=LOG_SUCCESS, no_date=True)
                        if unzipped != 0:
                            log(f'Error unzipping {zipfile} to {build_os_path}', log_type=LOG_ERROR, no_date=True)
                            return 56
                    else:
                        log("OK", log_type=LOG_SUCCESS, no_date=True)

                    s3path = f'UCB/unity-builds/{package_name}/ucb{build_target.name}.zip'
                    log(f'  Uploading copy to S3 {s3path} ...', end="")
                    if not simulate:
                        ok = s3_upload_file(zipfile, CFG['aws']['s3bucket'], s3path)
                    else:
                        ok = 0

                    if ok != 0:
                        log(f'Error uploading file "ucb{build_target.name}.zip" to AWS {s3path}. Check the IAM permissions',
                            log_type=LOG_ERROR, no_date=True)
                        return 9
                    log("OK", log_type=LOG_SUCCESS, no_date=True)

    log("--------------------------------------------------------------------------", no_date=True)
    log("Get version from source file...")
    for package_name, package in CFG_packages.items():
        if package.complete:
            build_targets = package.get_build_targets()
            for build_target in build_targets:
                build_os_path = f"{steam_build_path}/{build_target.name}"

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
                            log(" " + steam_appversion + " ", log_type=LOG_INFO, no_date=True, end="")
                            log("OK ", log_type=LOG_SUCCESS, no_date=True)
                    else:
                        log(f"File version UCB_version.txt was not found in build directory {build_os_path}",
                            log_type=LOG_WARNING, no_date=True)

    if not no_upload:
        log("--------------------------------------------------------------------------", no_date=True)
        log("Uploading files to stores...")

        for package_name, package in CFG_packages.items():
            package.uploaded = False

        # region STEAM
        for package_name, package in CFG_packages.items():
            first = True
            # we only want to build the packages that are complete
            if Store.STEAM in package.stores:
                if package.complete:
                    log(f'Starting Steam process for package {package_name}...')
                    app_id = ""

                    for build_target_id, build_target in package.stores[Store.STEAM].items():
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
                                shutil.copyfile(f"{steam_scripts_path}/template_app_build.vdf",
                                                f"{steam_scripts_path}/app_build_{app_id}.vdf")

                                replace_in_file(f"{steam_scripts_path}/app_build_{app_id}.vdf",
                                                "%basepath%", CFG['basepath'])
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

                            log("OK", log_type=LOG_SUCCESS, no_date=True)

                            # then the depot files
                        log(f' Preparing platform Steam file for depot {depot_id} / {build_target_id}...',
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
                                "%basepath%", CFG['basepath'])

                            data = vdf.load(open(f"{steam_scripts_path}/app_build_{app_id}.vdf"))
                            data['appbuild']['depots'][depot_id] = f"depot_build_{build_target_id}.vdf"

                            indented_vdf = vdf.dumps(data, pretty=True)

                            write_in_file(f"{steam_scripts_path}/app_build_{app_id}.vdf",
                                          indented_vdf)

                        log("OK", log_type=LOG_SUCCESS, no_date=True)

                    log(" Building Steam packages...", end="")
                    if app_id != "":
                        cmd = f'''{steam_exe_path} +login "{CFG['steam']['user']}" "{CFG['steam']['password']}" +run_app_build {steam_scripts_path}/app_build_{app_id}.vdf +quit'''
                        if not simulate:
                            ok = os.system(cmd)
                        else:
                            ok = 0

                        if ok != 0:
                            log(f" Executing the bash file {steam_exe_path} (exitcode={ok})",
                                log_type=LOG_ERROR, no_date=True)
                            return 9

                        package.uploaded = True

                        log("OK", log_type=LOG_SUCCESS, no_date=True)

                        if simulate:
                            log("  " + cmd)
                    else:
                        log("app_id is empty", log_type=LOG_ERROR, no_date=True)
                        return 9
                else:
                    if package.concerned:
                        log(f' Package {package_name} is not complete and will not be processed for Steam...',
                            log_type=LOG_WARNING)
        # endregion

        # region BUTLER
        for package_name, package in CFG_packages.items():
            # we only want to build the packages that are complete
            if Store.ITCH in package.stores:
                if package.complete:
                    log(f'Starting Butler process for package {package_name}...')

                    for build_target_id, build_target in package.stores[Store.ITCH].items():
                        # find the data related to the branch we want to build
                        butler_channel = build_target.parameters['channel']
                        build_path = f"{steam_build_path}/{build_target_id}"

                        log(f" Building itch.io(Butler) {build_target_id} packages...", end="")
                        cmd = f"{CFG['basepath']}/Butler/butler push {build_path} {CFG['butler']['org']}/{CFG['butler']['project']}:{butler_channel} --userversion={steam_appversion} --if-changed"
                        if not simulate:
                            ok = os.system(cmd)
                        else:
                            ok = 0

                        if ok != 0:
                            log(f"Executing Butler {CFG['basepath']}/Butler/butler (exitcode={ok})",
                                log_type=LOG_ERROR)
                            return 10

                        package.uploaded = True

                        log("OK", log_type=LOG_SUCCESS, no_date=True)

                        if simulate:
                            log("  " + cmd)
                else:
                    if package.concerned:
                        log(f' Package {package_name} is not complete and will not be processed for Butler...',
                            log_type=LOG_WARNING)
        # endregion

    if not no_clean:
        log("--------------------------------------------------------------------------", no_date=True)
        log("Cleaning successfully upload build in UCB...")
        # let's remove the build successfully uploaded to Steam or Butler from UCB
        # clean only the packages that are successful
        for package_name, package in CFG_packages.items():
            if package.complete and package.uploaded:
                log(f" Cleaning package {package_name}...")
                build_targets = package.get_build_targets()
                for build_target in build_targets:
                    # cleanup everything related to this package
                    for build in UCB.builds_categorized['success'] + UCB.builds_categorized['building'] + \
                                 UCB.builds_categorized['failure'] + \
                                 UCB.builds_categorized[
                                     'canceled']:
                        if build.build_target_id == build_target.name:
                            log(f"  Deleting build #{build.number} for buildtarget {build_target.name} (status: {build.status})...",
                                end="")
                            if not simulate:
                                UCB.delete_build(build_target.name, build.number)
                            log("OK", log_type=LOG_SUCCESS, no_date=True)

    log("--------------------------------------------------------------------------", no_date=True)
    log("All done!")
    return 0


if __name__ == "__main__":
    # load the configuration from the config file
    current_path = os.path.dirname(os.path.abspath(__file__))
    with open(current_path + '/UCB-steam.config', "r") as yml_file:
        CFG = yaml.load(yml_file, Loader=yaml.FullLoader)

    if CFG is None:
        code_ok = 11
        exit()

    # create the log directory if it does not exists
    if not os.path.exists(f"{CFG['logpath']}"):
        os.mkdir(f"{CFG['logpath']}")
    # set the log file name with the current datetime
    DEBUG_FILE_NAME = CFG['logpath'] + '/' + datetime.now().strftime("%Y%m%d_%H%M%S") + '.html'
    # open the logfile for writing
    DEBUG_FILE = open(DEBUG_FILE_NAME, "wt")

    code_ok = 0
    no_shutdown = False
    no_email = False
    try:
        options, arguments = getopt.getopt(sys.argv[1:], "hldocsfip:lv:t:u:a:",
                                           ["help", "nolive", "nodownload", "noupload", "noclean", "noshutdown",
                                            "noemail",
                                            "force", "install", "simulate", "showconfig", "showdiag", "platform=",
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
        print_help()
        code_ok = 11

    if code_ok != 10 and code_ok != 11:
        code_ok = main(sys.argv[1:])
        if not no_shutdown and code_ok != 10:
            log("Shutting down computer...")
            os.system("sudo shutdown +3")

    log("--- Script execution time : %s seconds ---" % (time.time() - start_time))
    # close the logfile
    DEBUG_FILE.close()
    if code_ok != 10 and code_ok != 11 and not no_email:
        send_email(CFG['email']['from'], CFG['email']['recipients'], "Steam build result",
                   read_from_file(DEBUG_FILE_NAME))
