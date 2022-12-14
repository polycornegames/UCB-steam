import json
import os
import socket
import time

import boto3
from botocore.exceptions import ClientError

region = os.environ['REGION_ID']
ec2instance = os.environ['INSTANCE_ID']
s3bucket = os.environ['S3_BUCKET']


def lambda_handler(event, context):
    print(event)
    if event['body'] is None:
        print(f'Nothing provided within the request')
        return False

    body = json.loads(event['body'])
    if body['buildTargetName'] is None:
        print(f'Missing parameters')
        return False

    buildTargetName = body['buildTargetName']
    branch = ""
    if buildTargetName.startswith("PROD"):
        branch = "prod"
    elif buildTargetName.startswith("BETA"):
        branch = "beta"
    elif buildTargetName.startswith("DEVELOP"):
        branch = "develop"
    else:
        print(f'Missing branch')
        return False

    s3_path = "UCB/steam-parameters/UCB-parameters.conf"
    stringtowrite = branch + ",0.31"
    send_string_to_s3file(s3_path, stringtowrite)

    result = start_instance(ec2instance)
    if not result:
        print(f'Startup of Instance {ec2instance} failed')
        return False
    else:
        print(f'Instance {ec2instance} started')

    return "Done"


def start_instance(instanceid):
    returncode = False
    ec2 = boto3.resource('ec2')
    ec2client = boto3.client('ec2', region_name=region)
    objinstance = ec2.Instance(id=instanceid)

    print(f' Instance {instanceid} is in state {objinstance.state["Name"]}')
    if objinstance.state["Code"] != 16:
        print(f' Starting instance {instanceid}...')
        ec2client.start_instances(InstanceIds=[instanceid])
    else:
        print(f'  No need to start it again')

    print(f' Waiting for instance to start (step 1)...')
    objinstance.wait_until_running(
        Filters=[
            {
                'Name': 'instance-id',
                'Values': [
                    instanceid,
                ]
            },
        ]
    )

    objinstance.reload()
    print(
        f' Instance {instanceid} in status {objinstance.state["Name"]} started with DNSname {objinstance.public_dns_name}')

    print(f' Waiting for instance to start (step 2)...')
    retries = 10
    retry_delay = 10
    retry_count = 0
    while retry_count <= retries:
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            result = sock.connect_ex((objinstance.public_ip_address, 22))
            if result == 0:
                print(f' Instance is UP & accessible on port 22, the IP address is: {objinstance.public_ip_address}')
                break
            else:
                print(" Instance is still down retrying...")
                time.sleep(retry_delay)
            retry_count = retry_count + 1
        except ClientError as e:
            retry_count = retry_count + 1
            print(f' Error {e}')

    if objinstance.state["Code"] == 16:
        returncode = True

    return returncode


def send_string_to_s3file(s3path, stringtowrite):
    encoded_string = stringtowrite.encode("utf-8")

    s3_client = boto3.client('s3', region_name=region)
    s3_client.put_object(Bucket=s3bucket, Key=s3path, Body=encoded_string)
