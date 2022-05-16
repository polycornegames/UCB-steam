from typing import Optional

from librairies import CFG
from librairies.AWS.aws import PolyAWSS3, PolyAWSSES, PolyAWSDynamoDB

print('AWS module loaded')

AWS_S3: Optional[PolyAWSS3] = None
AWS_SES: Optional[PolyAWSSES] = None
AWS_DDB: Optional[PolyAWSDynamoDB] = None

if 'aws' in CFG.settings:
    AWS_S3 = PolyAWSS3(CFG.settings['aws']['region'], CFG.settings['aws']['s3bucket'])
    AWS_SES = PolyAWSSES(CFG.settings['aws']['region'])
    AWS_DDB = PolyAWSDynamoDB(CFG.settings['aws']['region'], CFG.settings['aws']['dynamodbtablepackages'], "", "")
