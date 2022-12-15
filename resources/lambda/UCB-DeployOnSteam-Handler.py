import json
import os
import socket
import time
import uuid
from datetime import datetime

import boto3
from botocore.exceptions import ClientError

region: str = os.environ['REGION_ID']
ec2instance: str = os.environ['INSTANCE_ID']
s3bucket: str = os.environ['S3_BUCKET']
ddb_table_package_queue: str = os.environ['DDB_TABLE_PACKAGE_QUEUE']

enabled_str: str = os.environ['ENABLED']
enabled: bool = False
if enabled_str:
    enabled = os.environ['ENABLED'].lower() == 'true'

debug_str: str = os.environ['DEBUG']
debug: bool = False
if debug_str:
    debug = os.environ['DEBUG'].lower() == 'true'


def lambda_handler(event, context):
    if enabled:
        eventBody = event.get("body")
        if eventBody is None:
            print(f'Nothing provided within the request')
            return False

        if debug:
            print(event)

        body = json.loads(eventBody)
        build_number_str: str = body.get("buildNumber")
        build_number: int = -1
        build_target_id: str = body.get("buildTargetName")
        build_target_id = build_target_name_to_id(build_target_id)

        if build_number_str is None:
            print(f'Missing parameters buildNumber')
            return False
        else:
            build_number = int(build_number_str)

        if build_target_id is None:
            print(f'Missing parameters buildTargetName')
            return False

        insert_build_target_in_queue(build_target_id, build_number)

        if not debug:
            result = start_instance(ec2instance)
            if not result:
                print(f'Startup of Instance {ec2instance} failed')
                return False
            else:
                print(f'Instance {ec2instance} started')

        return "Done"
    else:
        return "Disabled"


def start_instance(instance_id):
    return_code = False
    ec2 = boto3.resource('ec2')
    ec2client = boto3.client('ec2', region_name=region)
    obj_instance = ec2.Instance(id=instance_id)

    print(f' Instance {instance_id} is in state {obj_instance.state["Name"]}')
    if obj_instance.state["Code"] != 16:
        print(f' Starting instance {instance_id}...')
        ec2client.start_instances(InstanceIds=[instance_id])
    else:
        print(f'  No need to start it again')

    print(f' Waiting for instance to start (step 1)...')
    obj_instance.wait_until_running(
        Filters=[
            {
                'Name': 'instance-id',
                'Values': [
                    instance_id,
                ]
            },
        ]
    )

    obj_instance.reload()
    print(
        f' Instance {instance_id} in status {obj_instance.state["Name"]} started with DNSname {obj_instance.public_dns_name}')

    print(f' Waiting for instance to start (step 2)...')
    retries = 10
    retry_delay = 10
    retry_count = 0
    while retry_count <= retries:
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            result = sock.connect_ex((obj_instance.public_ip_address, 22))
            if result == 0:
                print(f' Instance is UP & accessible on port 22, the IP address is: {obj_instance.public_ip_address}')
                break
            else:
                print(" Instance is still down retrying...")
                time.sleep(retry_delay)
            retry_count = retry_count + 1
        except ClientError as e:
            retry_count = retry_count + 1
            print(f' Error {e}')

    if obj_instance.state["Code"] == 16:
        return_code = True

    return return_code


def send_string_to_s3file(s3path, string_to_write):
    encoded_string = string_to_write.encode("utf-8")

    s3_client = boto3.client('s3', region_name=region)
    s3_client.put_object(Bucket=s3bucket, Key=s3path, Body=encoded_string)


def build_target_name_to_id(build_target_name: str) -> str:
    result: str

    result = build_target_name.lower()
    result = result.replace(" ", "-")
    result = result.replace("---", "-")

    return result


def insert_build_target_in_queue(build_target_id: str, build_number: int):
    aws_client = boto3.resource("dynamodb", region_name=region)
    table = aws_client.Table(ddb_table_package_queue)

    try:
        result = table.put_item(Item={
            "id": str(uuid.uuid4()),
            "build_number": build_number,
            "build_target_id": build_target_id,
            "date_inserted": datetime.now().strftime("%Y/%m/%d %H:%M:%S"),
            "date_processed": "",
            "processed": False
        })
    except ClientError as e:
        print(e.response['Error']['Message'])
        return False
    else:
        return True
