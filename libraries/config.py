import json
import os
from typing import Dict, Any, List
import yaml
from pathlib import Path


class Config:
    def __init__(self):
        # totally enable/disable the processing of the builds
        self.processing_enabled: bool = True

        # if set to False, then some values must be provided manually using 'set' functions below
        # for other values, default will be used
        self.use_config_file: bool = True

        # load the configuration from the config file
        self.config_file_path: str = ""
        self.config_base_path: str = ""

        # maximum time in minutes until the script will accept a build as valid
        self.build_max_age: int = 180

        # enable the debug verbose log
        self.debug: bool = False

        # if set to true, the version number will be used to identify if the build has already
        # been downloaded to avoid unuseful traffic
        self.check_project_version: bool = False

        # not use for now
        self.clean_uploaded_build: bool = True

        # if set to true, the build will be downloaded from UCB no matter if the version
        # is the same or not (no cache)
        self.force_download: bool = False

        # if set to true, the settings in the dynamodDB settings table will override the config file
        # settings
        self.use_dynamodb_for_settings: bool = True

        # the home path to the current user running the script
        self.home_path = Path.home()

        # the path containing the scripts files
        self.base_path = Path(__file__).parent.parent.absolute()

        # the path where the script will write the logs
        self.log_path = f"{self.base_path}/logs"

        # the path where the downloaded .zip will be extracted
        self.build_path = f"{self.base_path}/builds"

        # the path where the UCB builds will be downloaded
        self.download_path = f"{self.base_path}/downloads"

        # the number of minute the script will wait until shutdown the computer
        self.shutdown_delay = 0

        self.email: EmailConfig = EmailConfig()
        self.unity: Dict[str, Any] = {}
        self.aws: Dict[str, Any] = {
            "dynamodbtablepackages": "UCB-Packages",
            "dynamodbtablesettings": "UCB-Settings",
            "dynamodbtableunitybuildsqueue": "UCB-UnityBuildsQueue"
        }

        self.stores: Dict[str, Any] = {}
        self.hooks: Dict[str, Any] = {}

    def load(self, config_file_path: str = "", use_config_file: bool = True):
        self.use_config_file = use_config_file
        self.config_file_path = config_file_path

        # load the configuration from the config file
        if self.use_config_file:
            if os.path.exists(self.config_file_path):
                print(f"Using config file at '{self.config_file_path}'")
                self.config_base_path: str = self.config_file_path[:self.config_file_path.index('/')]
            else:
                raise f"Configuration file not found at '{self.config_file_path}'"

            # load the default values
            self.email.recipients.clear()
            self.unity.clear()
            self.aws = {
                "dynamodbtablepackages": "UCB-Packages",
                "dynamodbtablesettings": "UCB-Settings",
                "dynamodbtableunitybuildsqueue": "UCB-UnityBuildsQueue"
            }

            self.stores.clear()
            self.hooks.clear()

            if self.config_file_path and self.use_config_file:
                file_settings: dict = dict()
                with open(self.config_file_path, "r") as yml_file:
                    file_settings = yaml.load(yml_file, Loader=yaml.FullLoader)

                self.__fetch_values(file_settings.items())
        else:
            self.config_base_path: str = ""

    def set_AWS_region(self, region: str):
        self.aws['region'] = region

    def set_S3_bucket(self, s3_bucket: str):
        self.aws['s3bucket'] = s3_bucket

    def set_debug(self, debug: bool):
        self.debug = debug

    def load_DDB_config(self) -> int:
        from libraries import LOGGER
        from libraries.logger import LogLevel
        from libraries.AWS import AWS_DDB
        from libraries.common import errors
        import botocore
        from botocore.exceptions import ClientError

        LOGGER.log(f"Retrieving configuration from DynamoDB (table {AWS_DDB.dynamodb_table_settings})...", end="")

        try:
            parameters_data: Dict[str, object] = AWS_DDB.get_parameters_data()
            self.__fetch_values(parameters_data.items())
        except botocore.exceptions.EndpointConnectionError as e:
            LOGGER.log(e.fmt, log_type=LogLevel.LOG_ERROR, no_date=True)
            return errors.AWS_DDB_CONNECTION_FAILED1
        except ClientError as e:
            LOGGER.log(e.response['Error']['Message'], log_type=LogLevel.LOG_ERROR, no_date=True)
            return errors.AWS_DDB_CONNECTION_FAILED2
        LOGGER.log("OK", no_date=True, log_type=LogLevel.LOG_SUCCESS)

        return 0

    def __fetch_values(self, parameters):
        from libraries import LOGGER

        for key, value in parameters:
            if key == "buildmaxage":
                self.build_max_age = value
            elif key == "debug":
                self.debug = value
                if LOGGER:
                    LOGGER.debug = self.debug
            elif key == "processingenabled":
                self.processing_enabled = value
            elif key == "checkprojectversion":
                self.check_project_version = value
            elif key == "cleanuploadedbuild":
                self.clean_uploaded_build = value
            elif key == "forcedownload":
                self.force_download = value
            elif key == "usedynamodbforsettings":
                self.use_dynamodb_for_settings = value
            elif key == "shutdowndelay":
                self.shutdown_delay = value
            elif key == "homepath":
                self.home_path = value
            elif key == "basepath":
                self.base_path = value
            elif key == "logpath":
                self.log_path = value
            elif key == "buildpath":
                self.buildpath = value
            elif key == "downloadpath":
                self.download_path = value
            elif key == "shutdowndelay":
                self.shutdown_delay = value
            elif key == "aws":
                for item in value:
                    self.aws[item] = value[item]
            elif key == "unity":
                for item in value:
                    self.unity[item] = value[item]
            elif key == "hooks":
                for item in value:
                    self.hooks[item] = value[item]
            elif key == "stores":
                for item in value:
                    self.stores[item] = value[item]
            elif key == "email":
                if 'from' in value:
                    self.email.sender = value['from']
                if 'recipients' in value:
                    self.email.recipients = value['recipients']

    def print_config(self):
        from libraries import LOGGER

        LOGGER.log(f' processing_enabled : {self.processing_enabled}', no_date=True)
        LOGGER.log(f' use_config_file : {self.use_config_file}', no_date=True)
        LOGGER.log(f' config_file_path : {self.config_file_path}', no_date=True)
        LOGGER.log(f' config_base_path : {self.config_base_path}', no_date=True)
        LOGGER.log(f' build_max_age : {self.build_max_age}', no_date=True)
        LOGGER.log(f' debug : {self.debug}', no_date=True)
        LOGGER.log(f' check_project_version : {self.check_project_version}', no_date=True)
        LOGGER.log(f' clean_uploaded_build : {self.clean_uploaded_build}', no_date=True)
        LOGGER.log(f' force_download : {self.force_download}', no_date=True)
        LOGGER.log(f' use_dynamodb_for_settings : {self.use_dynamodb_for_settings}', no_date=True)
        LOGGER.log(f' home_path : {self.home_path}', no_date=True)
        LOGGER.log(f' base_path : {self.base_path}', no_date=True)
        LOGGER.log(f' log_path : {self.log_path}', no_date=True)
        LOGGER.log(f' build_path : {self.build_path}', no_date=True)
        LOGGER.log(f' download_path : {self.download_path}', no_date=True)
        LOGGER.log(f' shutdown_delay : {self.shutdown_delay}', no_date=True)

        LOGGER.log(f'email', no_date=True)
        LOGGER.log(f' from : {self.email.sender}', no_date=True)
        LOGGER.log(f' recipients :', no_date=True)
        for value in self.email.recipients:
            LOGGER.log(f'  {value}', no_date=True)

        LOGGER.log(f'aws', no_date=True)
        for key, value in self.aws.items():
            LOGGER.log(f' {key} : {json.dumps(value, indent=2)}', no_date=True)

        LOGGER.log(f'unity', no_date=True)
        for key, value in self.unity.items():
            LOGGER.log(f' {key} : {json.dumps(value, indent=2)}', no_date=True)

        LOGGER.log(f'stores', no_date=True)
        for key, value in self.stores.items():
            LOGGER.log(f' {key} : {json.dumps(value, indent=2)}', no_date=True)

        LOGGER.log(f'hooks', no_date=True)
        for key, value in self.hooks.items():
            LOGGER.log(f' {key} : {json.dumps(value, indent=2)}', no_date=True)


class EmailConfig:
    def __init__(self):
        self.sender: str = ""
        self.recipients: List[str] = []
