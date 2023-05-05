__version__ = "0.33"

import json
import os
import socket
import time

import boto3
from botocore.exceptions import ClientError

import libraries
from libraries import *
from libraries import AWS, Unity, ExecutionMode
from libraries.AWS import *
from libraries.Unity import *
from libraries.logger import LogLevel
from libraries.common import errors

from libraries import EXECUTION_MODE

EXECUTION_MODE = ExecutionMode.LAMBDA

ec2instance: str = os.environ['INSTANCE_ID'] if 'INSTANCE_ID' in os.environ else ''

enabled_str: str = os.environ['ENABLED'] if 'ENABLED' in os.environ else ''
enabled: bool = False
if enabled_str:
    enabled = enabled_str.lower() == 'true'

debug_str: str = os.environ['DEBUG'] if 'DEBUG' in os.environ else ''
debug: bool = False
if debug_str:
    debug = debug_str.lower() == 'true'

force_all_str: str = os.environ['FORCE_ALL'] if 'FORCE_ALL' in os.environ else ''
force_all: bool = False
if force_all_str:
    force_all = force_all_str.lower() == 'true'

show_diag_str: str = os.environ['SHOW_DIAG'] if 'SHOW_DIAG' in os.environ else ''
show_diag: bool = False
if show_diag_str:
    show_diag = show_diag_str.lower() == 'true'

show_config_str: str = os.environ['SHOW_CONFIG'] if 'SHOW_CONFIG' in os.environ else ''
show_config: bool = False
if show_config_str:
    show_config = show_config_str.lower() == 'true'

simulate_str: str = os.environ['SIMULATE'] if 'SIMULATE' in os.environ else ''
simulate: bool = False
if simulate_str:
    simulate = simulate_str.lower() == 'true'


def lambda_handler(event, context):
    exitcode: int = 0

    if enabled:
        CFG.set_debug(debug)
        CFG.set_AWS_region(os.environ['UCB_AWS_REGION'])
        CFG.set_S3_bucket(os.environ['UCB_AWS_S3BUCKET'])

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

        # region INIT
        libraries.load(use_config_file=False)
        AWS.init()
        if AWS_DDB and CFG.use_dynamodb_for_settings:
            CFG.load_DDB_config()
        Unity.init()
        # endregion

        # region LOAD MANAGERS
        MANAGERS.load_managers()
        # endregion

        if simulate:
            LOGGER.log(f"Simulation flag is ENABLED, no action will be executed for real",
                       log_type=LogLevel.LOG_WARNING)

        # region PACKAGES CONFIG
        exitcode = MANAGERS.package_manager.load_config()

        if exitcode == 0:
            exitcode = MANAGERS.package_manager.load_queues()
        # endregion

        # region SHOW CONFIG PACKAGES
        if exitcode == 0 and show_config:
            LOGGER.log(f"Displaying main configuration...")
            CFG.print_config()
            LOGGER.log('', no_date=True)

            LOGGER.log(f"Displaying packages configuration...")
            MANAGERS.package_manager.print_config(with_diag=False)
            LOGGER.log('', no_date=True)

            return 0
        # endregion

        if not CFG.processing_enabled:
            LOGGER.log(f"Processing flag is disabled, nothing will be processed", log_type=LogLevel.LOG_INFO)
            return 0

        if not MANAGERS.package_manager.is_build_target_already_in_queue(build_target_id, build_number):
            AWS_DDB.insert_build_target_in_queue(build_target_id, build_number)

        # region DISPLAY FILTERED BUILDS
        if exitcode == 0 and len(MANAGERS.package_manager.filtered_builds) == 0:
            if force_all:
                LOGGER.log("No build available in UCB but process forced to continue (--forceall flag used)",
                           log_type=LogLevel.LOG_WARNING,
                           no_date=True)
            elif show_diag:
                LOGGER.log("No build available in UCB but process forced to continue (--showdiag flag used)",
                           log_type=LogLevel.LOG_WARNING,
                           no_date=True)
            else:
                LOGGER.log("No build available in UCB", log_type=LogLevel.LOG_SUCCESS, no_date=True)
                exitcode = errors.UCB_NO_BUILD_AVAILABLE

        # filter on successful builds only
        UCB.display_builds_details()

        # endregion

        # region SHOW DIAG
        if exitcode == 0 and show_diag:
            LOGGER.log(f"Displaying diagnostics...")
            LOGGER.log('', no_date=True)

            MANAGERS.package_manager.print_config(with_diag=True)

            return 0
        # endregion

        if exitcode == 0:
            can_continue = False
            for package in MANAGERS.package_manager.packages.values():
                if package.complete:
                    can_continue = True

            LOGGER.log("One or more packages complete...", end="")
            if can_continue:
                LOGGER.log("OK", no_date=True, log_type=LogLevel.LOG_SUCCESS)
            elif force_all:
                LOGGER.log(f"Process forced to continue (--forceall flag used)", no_date=True,
                           log_type=LogLevel.LOG_WARNING, no_prefix=True)
            else:
                LOGGER.log("At least one package must be complete to proceed to the next step", no_date=True,
                           log_type=LogLevel.LOG_ERROR, no_prefix=True)
                exitcode = errors.NO_PACKAGE_COMPLETE

        if exitcode == 0:
            if not simulate:
                result = start_instance(ec2instance)
                if not result:
                    LOGGER.log(f'Startup of Instance {ec2instance} failed')
                    return False
                else:
                    LOGGER.log(f'Instance {ec2instance} started')

        if exitcode == 0:
            return "Done"
        else:
            return "Fail"
    else:
        return "Disabled"


def start_instance(instance_id):
    return_code = False
    ec2 = boto3.resource('ec2')
    ec2client = boto3.client('ec2', region_name=CFG.aws['region'])
    obj_instance = ec2.Instance(id=instance_id)

    LOGGER.log(f' Instance {instance_id} is in state {obj_instance.state["Name"]}')
    if obj_instance.state["Code"] != 16:
        LOGGER.log(f' Starting instance {instance_id}...')
        ec2client.start_instances(InstanceIds=[instance_id])
    else:
        LOGGER.log(f'  No need to start it again')

    LOGGER.log(f' Waiting for instance to start (step 1)...')
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
    LOGGER.log(
        f' Instance {instance_id} in status {obj_instance.state["Name"]} started with DNSname {obj_instance.public_dns_name}')

    LOGGER.log(f' Waiting for instance to start (step 2)...')
    retries = 10
    retry_delay = 10
    retry_count = 0
    while retry_count <= retries:
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            result = sock.connect_ex((obj_instance.public_ip_address, 22))
            if result == 0:
                LOGGER.log(f' Instance is UP & accessible on port 22, the IP address is: {obj_instance.public_ip_address}')
                break
            else:
                LOGGER.log(" Instance is still down retrying...")
                time.sleep(retry_delay)
            retry_count = retry_count + 1
        except ClientError as e:
            retry_count = retry_count + 1
            LOGGER.log(f' Error {e}', log_type=LogLevel.LOG_ERROR)

    if obj_instance.state["Code"] == 16:
        return_code = True

    return return_code


def build_target_name_to_id(build_target_name: str) -> str:
    result: str

    result = build_target_name.lower()
    result = result.replace(" ", "-")
    result = result.replace("---", "-")

    return result
