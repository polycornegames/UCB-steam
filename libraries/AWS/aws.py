import os
import uuid
from datetime import datetime
from typing import Optional, List, Dict
from pathlib import Path

import boto3
from boto3.dynamodb.conditions import Attr
from botocore.client import BaseClient
from botocore.exceptions import ClientError

from libraries import LOGGER
from libraries.logger import LogLevel


class PolyAWSS3:
    def __init__(self):
        self._aws_region: str = ""
        self._aws_bucket: str = ""
        self.connected: bool = False
        self._aws_client: Optional[BaseClient] = None

    def init(self, aws_region: str, aws_bucket: str):
        self._aws_region: str = aws_region
        self._aws_bucket: str = aws_bucket
        self.connected: bool = False
        self._aws_client: Optional[BaseClient] = None

    @property
    def aws_bucket(self):
        return self._aws_bucket

    @property
    def aws_region(self):
        return self._aws_region

    def __connect_boto3(self):
        try:
            self._aws_client: BaseClient = boto3.client("s3", region_name=self._aws_region)
        except ClientError as e:
            LOGGER.log(e.response['Error']['Message'], log_type=LogLevel.LOG_ERROR)
            return 470

    def s3_download_file(self, file: str, destination_path: str) -> int:
        if not self.connected:
            self.__connect_boto3()

        try:
            # Provide the file information to upload.
            self._aws_client.download_file(
                Filename=destination_path,
                Bucket=self._aws_bucket,
                Key=file,
            )
            return 0
        # Display an error if something goes wrong.
        except ClientError as e:
            LOGGER.log(e.response['Error']['Message'], log_type=LogLevel.LOG_ERROR)
            return 440

    def s3_list_files(self, directory: str) -> List[str]:
        if not self.connected:
            self.__connect_boto3()

        try:
            file_names: List[str] = list()

            default_kwargs = {
                "Bucket": self._aws_bucket,
                "Prefix": directory
            }
            next_token = ""

            while next_token is not None:
                updated_kwargs = default_kwargs.copy()
                if next_token != "":
                    updated_kwargs["ContinuationToken"] = next_token

                response = self._aws_client.list_objects_v2(**default_kwargs)
                contents = response.get("Contents")

                for result in contents:
                    key = result.get("Key")
                    file_names.append(key)

                next_token = response.get("NextContinuationToken")

            return file_names
        # Display an error if something goes wrong.
        except ClientError as e:
            LOGGER.log(e.response['Error']['Message'], log_type=LogLevel.LOG_ERROR)
            return 441

    def s3_download_directory(self, directory: str, destination_path: str) -> int:
        if not self.connected:
            self.__connect_boto3()

        try:
            file_names: List[str] = self.s3_list_files(directory)

            local_path: Path = Path(destination_path)

            for file_name in file_names:
                target = file_name if destination_path is None \
                    else os.path.join(destination_path, os.path.relpath(file_name, directory))
                if not os.path.exists(os.path.dirname(target)):
                    os.makedirs(os.path.dirname(target))
                if file_name[-1] == '/':
                    continue

                self._aws_client.download_file(
                    Filename=target,
                    Bucket=self._aws_bucket,
                    Key=file_name,
                )

            return 0
        # Display an error if something goes wrong.
        except ClientError as e:
            print(e)
            LOGGER.log(e.response['Error']['Message'], log_type=LogLevel.LOG_ERROR)
            return 440

    def s3_upload_file(self, file_to_upload_path: str, destination_path: str) -> int:
        if not self.connected:
            self.__connect_boto3()

        try:
            self._aws_client.put_object(
                Bucket=self._aws_bucket,
                Key=destination_path,
                Body=open(file_to_upload_path, 'rb')
            )

            return 0
        # Display an error if something goes wrong.
        except ClientError as e:
            LOGGER.log(e.response['Error']['Message'], log_type=LogLevel.LOG_ERROR)
            return 450

    def s3_delete_file(self, file_to_delete_path: str) -> int:
        if not self.connected:
            self.__connect_boto3()

        try:
            self._aws_client.put_object(
                Bucket=self._aws_bucket,
                Key=file_to_delete_path
            )

            return 0
        # Display an error if something goes wrong.
        except ClientError as e:
            LOGGER.log(e.response['Error']['Message'], log_type=LogLevel.LOG_ERROR)
            return 460


class PolyAWSDynamoDB:
    def __init__(self):
        self._aws_region: str = ""
        self._dynamodb_table_packages: str = ""
        self._dynamodb_table_unity_builds_queue: str = ""
        self._dynamodb_table_settings: str = ""
        self._dynamodb_table_queue: str = ""
        self._dynamodb_table_build_targets: str = ""

    def init(self, aws_region: str, dynamodb_table_packages: str, dynamodb_table_UCB_builds_queue: str,
             dynamodb_table_settings: str, dynamodb_table_queue: str, dynamodb_table_build_targets: str):
        self._aws_region = aws_region
        self._dynamodb_table_packages = dynamodb_table_packages
        self._dynamodb_table_unity_builds_queue = dynamodb_table_UCB_builds_queue
        self._dynamodb_table_settings = dynamodb_table_settings
        self._dynamodb_table_queue = dynamodb_table_queue
        self._dynamodb_table_build_targets = dynamodb_table_build_targets

        self.__connect_dynamodb()

    @property
    def aws_region(self):
        return self._aws_region

    @property
    def dynamodb_table_settings(self):
        return self._dynamodb_table_settings

    @property
    def dynamodb_table_packages(self):
        return self._dynamodb_table_packages

    @property
    def dynamodb_table_packages_queue(self):
        return self._dynamodb_table_unity_builds_queue

    @property
    def dynamodb_table_queue(self):
        return self._dynamodb_table_queue

    @property
    def dynamodb_table_build_targets(self):
        return self._dynamodb_table_build_targets

    def __connect_dynamodb(self):
        self._aws_client = boto3.resource("dynamodb", region_name=self._aws_region)

    def get_parameters_data(self) -> Dict[str, object]:
        table = self._aws_client.Table(self._dynamodb_table_settings)

        response = table.scan(
            ProjectionExpression="#n, #v",
            ExpressionAttributeNames={'#n': 'name', '#v': 'value'}
        )
        items = response['Items']
        while 'LastEvaluatedKey' in response:
            response = table.scan(ExclusiveStartKey=response['LastEvaluatedKey'])
            items.extend(response['Items'])

        data: Dict[str, object] = {item['name']: item['value'] for item in items}

        return data

    def get_packages_data(self) -> List:
        table = self._aws_client.Table(self._dynamodb_table_packages)

        response = table.scan(
            ProjectionExpression="id, stores, hooks, #p",
            ExpressionAttributeNames={'#p': 'parameters'}
        )
        data = response['Items']
        while 'LastEvaluatedKey' in response:
            response = table.scan(ExclusiveStartKey=response['LastEvaluatedKey'])
            data.extend(response['Items'])

        return data

    def get_builds_queue_data(self) -> List:
        table = self._aws_client.Table(self._dynamodb_table_unity_builds_queue)

        response = table.scan(
            ProjectionExpression="#i, #b, #n, #p",
            ExpressionAttributeNames={
                '#i': 'id',
                '#b': 'build_target_id',
                '#n': 'build_number',
                '#p': 'processed'
            },
            FilterExpression=Attr('processed').eq(False)
        )
        data = response['Items']
        while 'LastEvaluatedKey' in response:
            response = table.scan(ExclusiveStartKey=response['LastEvaluatedKey'])
            data.extend(response['Items'])

        return data

    def get_build_target(self, build_target_id: str):
        table = self._aws_client.Table(self._dynamodb_table_packages)

        try:
            response = table.get_item(Key={'id': build_target_id})
        except ClientError as e:
            print(e.response['Error']['Message'])
        else:
            return response['Item']

    def insert_build_target_in_queue(self, build_target_id: str, build_number: int):
        table = self._aws_client.Table(self._dynamodb_table_unity_builds_queue)

        try:
            result = table.put_item(Item={
                "id": str(uuid.uuid4()),
                "number": build_number,
                "build_target": build_target_id,
                "date_inserted": datetime.now().strftime("%Y/%m/%d %H:%M:%S"),
                "date_processed": "",
                "processed": False
            })
        except ClientError as e:
            print(e.response['Error']['Message'])
            return False
        else:
            return True

    def set_build_target_to_processed(self, queue_id: str) -> bool:
        table = self._aws_client.Table(self._dynamodb_table_unity_builds_queue)

        try:
            result = table.update_item(
                Key={
                    'id': queue_id,
                },
                UpdateExpression="set date_processed = :d, #p = :p",
                ExpressionAttributeNames={
                    '#p': 'processed'
                },
                ExpressionAttributeValues={
                    ':d': datetime.now().strftime("%Y/%m/%d %H:%M:%S"),
                    ':p': True,
                }
            )
        except ClientError as e:
            print(e.response['Error']['Message'])
            return False
        else:
            return True


class PolyAWSSES:
    def __init__(self):
        self._aws_region: str = ""

    def init(self, aws_region: str):
        self._aws_region = aws_region

        self.__connect_ses()

    @property
    def aws_region(self):
        return self._aws_region

    def __connect_ses(self):
        self._aws_client = boto3.client("ses", region_name=self._aws_region)

    def send_email(self, sender: str, recipients: str, title: str, message: str, quiet: bool = False) -> int:
        try:
            # Provide the contents of the email.
            response = self._aws_client.send_email(
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
            LOGGER.log(e.response['Error']['Message'], log_type=LogLevel.LOG_ERROR)
            return 461
        else:
            if not quiet:
                LOGGER.log("Email sent! Message ID:"),
                LOGGER.log(response['MessageId'])
            return 0

# endregion
