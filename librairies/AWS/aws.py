import os
from typing import Optional

import boto3
from botocore.client import BaseClient
from botocore.exceptions import ClientError

from librairies import LOGGER
from librairies.logger import LogLevel


class PolyAWSS3:
    def __init__(self, aws_region: str, aws_bucket: str):
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

    def s3_download_directory(self, directory: str, destination_path: str) -> int:
        if not self.connected:
            self.__connect_boto3()

        s3 = self._aws_client.resource("s3")
        try:
            bucket = s3.Bucket(self._aws_bucket)
            for obj in bucket.objects.filter(Prefix=directory):
                target = obj.key if destination_path is None \
                    else os.path.join(destination_path, os.path.relpath(obj.key, directory))
                if not os.path.exists(os.path.dirname(target)):
                    os.makedirs(os.path.dirname(target))
                if obj.key[-1] == '/':
                    continue
                self._aws_client.download_file(
                    Filename=target,
                    Bucket=self._aws_bucket,
                    Key=obj.key,
                )
            return 0
        # Display an error if something goes wrong.
        except ClientError as e:
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
    def __init__(self, aws_region: str, dynamodb_table: str):
        self._aws_region = aws_region
        self._dynamodb_table = dynamodb_table
        self.__connect_dynamodb()

    @property
    def aws_region(self):
        return self._aws_region

    def __connect_dynamodb(self):
        self._aws_client = boto3.resource("dynamodb", region_name=self._aws_region)

    def get_packages_data(self):
        table = self._aws_client.Table(self._dynamodb_table)

        response = table.scan(
            ProjectionExpression="id, stores, hooks"
        )
        data = response['Items']
        while 'LastEvaluatedKey' in response:
            response = table.scan(ExclusiveStartKey=response['LastEvaluatedKey'])
            data.extend(response['Items'])

        return data

    def get_build_target(self, build_target_id: str):
        table = self._aws_client.Table(self._dynamodb_table)

        try:
            response = table.get_item(Key={'id': build_target_id})
        except ClientError as e:
            print(e.response['Error']['Message'])
        else:
            return response['Item']

    # def get_build_targets(self, package_name: str):
    #    table = self._aws_client.Table(self._dynamodb_table)
    #
    #    try:
    #        response = table.query(
    #            KeyConditionExpression=Key('steam.package').eq(package_name) | Key('butler.package').eq(package_name)
    #        )
    #    except ClientError as e:
    #        print(e.response['Error']['Message'])
    #    else:
    #        return response['Item']


class PolyAWSSES:
    def __init__(self, aws_region: str):
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