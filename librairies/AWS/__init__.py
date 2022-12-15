from typing import Optional

from librairies import CFG
from librairies.AWS.aws import PolyAWSS3, PolyAWSSES, PolyAWSDynamoDB

print('AWS module loaded')

AWS_S3: Optional[PolyAWSS3] = None
AWS_SES: Optional[PolyAWSSES] = None
AWS_DDB: Optional[PolyAWSDynamoDB] = None

if CFG.aws is not None:
    AWS_S3 = PolyAWSS3(CFG.aws['region'], CFG.aws['s3bucket'])
    AWS_SES = PolyAWSSES(CFG.aws['region'])
    AWS_DDB = PolyAWSDynamoDB(aws_region=CFG.aws['region'],
                              dynamodb_table_packages=CFG.aws['dynamodbtablepackages'],
                              dynamodb_table_UCB_builds_queue=CFG.aws['dynamodbtableunitybuildsqueue'],
                              dynamodb_table_settings=CFG.aws['dynamodbtablesettings'],
                              dynamodb_table_queue="",
                              dynamodb_table_build_targets="")
