#!/usr/bin/env python3
"""
Configure S3 bucket to trigger Lambda function on CSV uploads to a specified folder path.

This script performs the following steps:
1. Retrieves AWS account ID and region using STS get-caller-identity.
2. Adds permission for S3 to invoke the specified Lambda function.
3. Configures S3 bucket notification to trigger the Lambda function on object creation events for CSV files in the specified folder path.

Usage:
    python configure_s3_trigger.py --bucket mybucketname --function my-lambda-function --profile myprofile --path folder1/folder2/
    python configure_s3_trigger.py -b mybucketname -f my-lambda-function -p myprofile -P data/incoming/
    python configure_s3_trigger.py -b mybucketname -f my-lambda-function -p myprofile
"""

import argparse
import boto3
from botocore.exceptions import ClientError
from datetime import datetime
import sys


def get_aws_account_info(profile_name):
    """
    Get AWS account ID and region using STS get-caller-identity.
    
    Args:
        profile_name: AWS profile name to use
        
    Returns:
        tuple: (account_id, region, session)
    """
    try:
        # Create session with the specified profile
        session = boto3.Session(profile_name=profile_name)
        
        # Get STS client
        sts_client = session.client('sts')
        
        # Get caller identity
        identity = sts_client.get_caller_identity()
        account_id = identity['Account']
        
        # Get region from session
        region = session.region_name
        
        print(f"AWS Account ID: {account_id}")
        print(f"AWS Region: {region}")
        print(f"User ARN: {identity['Arn']}")
        
        return account_id, region, session
        
    except ClientError as e:
        print(f"Error getting AWS account info: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)


def generate_timestamp():
    """
    Generate a timestamp string in YYYYmmddHHMMSS format.
    
    Returns:
        str: Timestamp string (e.g., '20260224143004')
    """
    return datetime.now().strftime('%Y%m%d%H%M%S')


def normalize_folder_path(path):
    """
    Normalize folder path to ensure it ends with a trailing slash.
    
    Args:
        path: Folder path (e.g., 'folder1/folder2' or 'folder1/folder2/')
        
    Returns:
        str: Normalized path with trailing slash
    """
    if not path:
        return ''
    
    # Remove leading slash if present
    if path.startswith('/'):
        path = path[1:]
    
    # Add trailing slash if not present
    if not path.endswith('/'):
        path = path + '/'
    
    return path


def add_lambda_permission(lambda_client, function_name, bucket_name, timestamp):
    """
    Add permission for S3 to invoke the Lambda function.
    
    Args:
        lambda_client: Boto3 Lambda client
        function_name: Name of the Lambda function
        bucket_name: Name of the S3 bucket
        timestamp: Timestamp string for unique StatementId
    """
    try:
        statement_id = f's3-csv-trigger-{timestamp}'
        
        response = lambda_client.add_permission(
            FunctionName=function_name,
            StatementId=statement_id,
            Action='lambda:InvokeFunction',
            Principal='s3.amazonaws.com',
            SourceArn=f'arn:aws:s3:::{bucket_name}'
        )
        print(f"Added Lambda permission for S3 to invoke {function_name}")
        print(f"   Statement ID: {statement_id}")
        
    except ClientError as e:
        if e.response['Error']['Code'] == 'ResourceConflictException':
            print(f"Permission already exists (statement ID: {statement_id})")
        else:
            print(f"Error adding Lambda permission: {e}")
            raise


def configure_s3_notification(s3_client, bucket_name, lambda_arn, folder_path, timestamp):
    """
    Configure S3 bucket notification to trigger Lambda on CSV uploads.
    
    Args:
        s3_client: Boto3 S3 client
        bucket_name: Name of the S3 bucket
        lambda_arn: ARN of the Lambda function
        folder_path: Folder path prefix for filtering
        timestamp: Timestamp string for unique notification Id
    """
    try:
        notification_id = f'csv-upload-trigger-{timestamp}'
        
        notification_configuration = {
            'LambdaFunctionConfigurations': [
                {
                    'Id': notification_id,
                    'LambdaFunctionArn': lambda_arn,
                    'Events': ['s3:ObjectCreated:*'],
                    'Filter': {
                        'Key': {
                            'FilterRules': [
                                {
                                    'Name': 'prefix',
                                    'Value': folder_path
                                },
                                {
                                    'Name': 'suffix',
                                    'Value': '.csv'
                                }
                            ]
                        }
                    }
                }
            ]
        }
        
        s3_client.put_bucket_notification_configuration(
            Bucket=bucket_name,
            NotificationConfiguration=notification_configuration
        )
        
        print(f"Configured S3 notification on bucket: {bucket_name}")
        print(f"   - Notification ID: {notification_id}")
        print(f"   - Prefix: {folder_path}")
        print(f"   - Suffix: .csv")
        print(f"   - Lambda ARN: {lambda_arn}")
        
    except ClientError as e:
        print(f"Error configuring S3 notification: {e}")
        raise


def parse_arguments():
    """
    Parse command line arguments.
    
    Returns:
        argparse.Namespace: Parsed arguments
    """
    parser = argparse.ArgumentParser(
        description='Configure S3 bucket to trigger Lambda function on CSV uploads to a specified folder path.',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --bucket mybucketname --function my-lambda-function --profile myprofile --path folder1/folder2/
  %(prog)s -b mybucketname -f my-lambda-function -p myprofile -P data/incoming/
  %(prog)s -b mybucketname -f my-lambda-function -p myprofile -P uploads/
  
  # Root of bucket (no prefix) - path is optional
  %(prog)s -b mybucketname -f my-lambda-function -p myprofile
  %(prog)s -b mybucketname -f my-lambda-function -p myprofile -P ""
  
Test after configuration:
  aws s3 cp myfile.csv s3://mybucketname/folder1/folder2/myfile.csv --profile myprofile
        """
    )
    
    parser.add_argument(
        '-b', '--bucket',
        required=True,
        help='S3 bucket name (e.g., mybucketname)'
    )
    
    parser.add_argument(
        '-f', '--function',
        required=True,
        help='Lambda function name (e.g., my-lambda-function)'
    )
    
    parser.add_argument(
        '-p', '--profile',
        required=True,
        help='AWS profile name to use for authentication'
    )
    
    parser.add_argument(
        '-P', '--path',
        required=False,
        default='',
        help='Folder path prefix for CSV files (e.g., folder1/folder2/ or data/incoming/). Defaults to root of bucket if not specified.'
    )
    
    return parser.parse_args()


def main():
    """Main function to configure S3 trigger for Lambda."""
    
    # Parse command line arguments
    args = parse_arguments()
    
    bucket_name = args.bucket
    lambda_function_name = args.function
    aws_profile = args.profile
    folder_path = normalize_folder_path(args.path)
    
    print("=" * 80)
    print("S3 LAMBDA TRIGGER CONFIGURATION")
    print("=" * 80)
    print(f"Bucket Name: {bucket_name}")
    print(f"Lambda Function: {lambda_function_name}")
    print(f"AWS Profile: {aws_profile}")
    print(f"Folder Path: {folder_path if folder_path else '(root of bucket)'}")
    print("-" * 80)
    
    # Get AWS account info using STS
    account_id, region, session = get_aws_account_info(aws_profile)
    
    # Create boto3 clients using the session
    lambda_client = session.client('lambda')
    s3_client = session.client('s3')
    
    # Construct Lambda ARN
    lambda_arn = f"arn:aws:lambda:{region}:{account_id}:function:{lambda_function_name}"
    
    # Generate timestamp for unique IDs
    timestamp = generate_timestamp()
    
    print("-" * 80)
    
    # Step 1: Add Lambda permission
    print("\nStep 1: Adding Lambda permission for S3...")
    add_lambda_permission(lambda_client, lambda_function_name, bucket_name, timestamp)
    
    # Step 2: Configure S3 notification
    print("\nStep 2: Configuring S3 bucket notification...")
    configure_s3_notification(s3_client, bucket_name, lambda_arn, folder_path, timestamp)
    
    print("\n" + "=" * 80)
    print("CONFIGURATION COMPLETE!")
    print("=" * 80)
    print(f"\nYour Lambda function '{lambda_function_name}' will now be triggered when")
    print(f"CSV files are uploaded to: s3://{bucket_name}/{folder_path}")
    print("\nTest by uploading a file:")
    print(f"  aws s3 cp myfile.csv s3://{bucket_name}/{folder_path}myfile.csv --profile {aws_profile}")
    

if __name__ == "__main__":
    main()
