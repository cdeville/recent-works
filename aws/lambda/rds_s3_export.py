# Standard libraries
import os

# Third-Party Libaries
import boto3
from botocore.exceptions import ClientError

# shared Libraries
from logging_utils import setup_logging
from shared_libs import get_formatted_datetime

logger = setup_logging()


"""
RDS Snapshot Export to S3 - Lambda Function

Purpose:
    Automatically exports RDS database snapshots to S3 in Parquet format for cross-account
    reporting and analytics. This enables sharing database data with reporting/analytics
    accounts without requiring direct database access or credentials.
"""


# Standard AWS Handler Function
def handler(event, context):
    """Lambda handler to start RDS snapshot export to S3."""

    logger.info("Received event: %s", event)
    timestamp = get_formatted_datetime()

    # Environment Variables
    S3Bucket = os.getenv("S3_BUCKET_NAME")
    DBExport = os.getenv("EXPORT_DB")
    KmsArn = os.getenv("KMS_ARN")
    RoleArn = os.getenv("ROLE_ARN")
    S3Prefix = os.getenv("S3_PREFIX")
    
    # Event Parameters
    SnapshotArn = event['detail']['SourceArn']
    # UniqueId used as an idempotency hack
    UniqueId = event['id']
    ExportTaskId = f"{timestamp}-{UniqueId}"

    logger.info(f"""
        Starting RDS export task with the following parameters:
        SnapshotArn: {SnapshotArn}
        S3Bucket: {S3Bucket}
        DBExport: {DBExport}
        KmsArn: {KmsArn}
        RoleArn: {RoleArn}
        S3Prefix: {S3Prefix}
        ExportTaskId: {ExportTaskId}
    """)

    try:
        rds = boto3.client('rds')
        RdsStart = rds.start_export_task(
            ExportTaskIdentifier=ExportTaskId,
            SourceArn=SnapshotArn,
            S3BucketName=S3Bucket,
            IamRoleArn=RoleArn,
            KmsKeyId=KmsArn,
            S3Prefix=S3Prefix,
            ExportOnly=[
                DBExport,
            ]
        )
        logger.info(f"Successfully started RDS export task: {RdsStart}")
    except ClientError as e:
        error_code = e.response['Error']['Code']
        # EventBridge can send multiple copies of the same event
        # Exit gracefully if this ExportTaskId already exists
        if error_code == "ExportTaskAlreadyExistsFault":
            logger.info(f"Export task '{ExportTaskId}' already exists. Exiting gracefully.")
            return
        else:
            logger.error(
                f"Error starting RDS export task '{ExportTaskId}' for snapshot '{SnapshotArn}': {e}"
            )
            raise