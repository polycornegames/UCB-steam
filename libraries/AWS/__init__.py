__all__ = ['PolyAWSS3', 'PolyAWSSES', 'PolyAWSDynamoDB', 'AWS_S3', 'AWS_SES', 'AWS_DDB', 'init']

from libraries import CFG, LOGGER
from libraries.AWS.aws import PolyAWSS3, PolyAWSSES, PolyAWSDynamoDB
from libraries.logger import LogLevel

print('AWS module loaded')

AWS_S3: PolyAWSS3 = PolyAWSS3()
AWS_SES: PolyAWSSES = PolyAWSSES()
AWS_DDB: PolyAWSDynamoDB = PolyAWSDynamoDB()


def init():
    if CFG.aws is not None and len(CFG.aws) > 0:
        if 'region' not in CFG.aws:
            LOGGER.log("'aws' configuration file section have no 'region' value", log_type=LogLevel.LOG_ERROR)
            return

        AWS_SES.init(CFG.aws['region'])

        if 's3bucket' in CFG.aws:
            AWS_S3.init(CFG.aws['region'], CFG.aws['s3bucket'])
        else:
            LOGGER.log("'aws' configuration file section have no 's3bucket' section", log_type=LogLevel.LOG_DEBUG)

        if 'dynamodbtablepackages' in CFG.aws and 'dynamodbtableunitybuildsqueue' in CFG.aws and 'dynamodbtablesettings' in CFG.aws:
            AWS_DDB.init(aws_region=CFG.aws['region'],
                         dynamodb_table_packages=CFG.aws['dynamodbtablepackages'],
                         dynamodb_table_UCB_builds_queue=CFG.aws['dynamodbtableunitybuildsqueue'],
                         dynamodb_table_settings=CFG.aws['dynamodbtablesettings'],
                         dynamodb_table_queue="",
                         dynamodb_table_build_targets="",
                         aws_access_key=CFG.aws['accesskey'],
                         aws_secret_key=CFG.aws['secretkey'])
        else:
            if 'dynamodbtablepackages' not in CFG.aws:
                LOGGER.log("'aws' configuration file section have no 'dynamodbtablepackages' section",
                           log_type=LogLevel.LOG_DEBUG)
            if 'dynamodbtableunitybuildsqueue' not in CFG.aws:
                LOGGER.log("'aws' configuration file section have no 'dynamodbtableunitybuildsqueue' section",
                           log_type=LogLevel.LOG_DEBUG)
            if 'dynamodbtablesettings' not in CFG.aws:
                LOGGER.log("'aws' configuration file section have no 'dynamodbtablesettings' section",
                           log_type=LogLevel.LOG_DEBUG)
