#!/usr/bin/env python3

"""
Purpose: Trigger GitHub Actions workflow dispatch event to deploy AWS Lambda function

  Requires:
  - GitHub CLI installed and authenticated (https://cli.github.com/)
    - gh cli NHME Instructions: 
        https://github.com/{myOrg}/itops_documentation/blob/main/ITOps%20Knowledge%20Base/GitHub_CLI_GH_Setup.md
  - PyGithub library (pip install PyGithub)
  - Boto3 library (pip install boto3)
  - AWS credentials configured with access to DynamoDB table
    - export AWS_PROFILE=<DEV_PROFILE_NAME>
"""

# Standard Python Libraries
import subprocess
import json
import argparse

# Third-Party Libraries
import boto3
from botocore.exceptions import ClientError
# Require PyGithub: pip install PyGithub
from github import Github, Auth

# Vars - needs to be parameterized in the future
myOrg = "myOrgName"
myRepo = f"{myOrg}/myRepoName"
myWorkflow = "deploy_lambda.yaml"
# DynamoDB table lives in Dev account
# We pull GitHub config from here
# export AWS_PROFILE=<DEV_PROFILE_NAME>
myDynamoDBTable = "myDynamoTableName"
myDynamoRegion = "us-east-2"

def runWorkflow(builddir, cftparam, environment, update, region):
    # Get token from gh cli
    token = subprocess.run(["gh", "auth", "token"], capture_output=True, text=True).stdout.strip()
    # Authenticate
    auth = Auth.Token(token)
    gh = Github(auth=auth)
    # Get repository
    repo = gh.get_repo(myRepo)

    # Trigger a workflow by dispatch event
    workflow = repo.get_workflow(myWorkflow)  # or use workflow ID
    workflow.create_dispatch(
        ref="main", 
        inputs={
            "build_dir": builddir,
            "cft_param_file": cftparam,
            "update_lambda": update,
            "environment": environment,
            "region": region
        }
    )

def get_lambda_functions_dict(table_name, region_name='us-east-2'):
    """
    Scan a DynamoDB table and create a dictionary of LambdaFuncName:  LambdaFuncValue
    
    Args:
        table_name (str): Name of the DynamoDB table
        region_name (str): AWS region name (default: 'us-east-2')
    
    Returns:
        dict: Dictionary with LambdaFuncName as keys and LambdaFuncValue as values
    """
    # Initialize DynamoDB client
    dynamodb = boto3.resource('dynamodb', region_name=region_name)
    table = dynamodb.Table(table_name)
    
    lambda_functions = {}
    
    try:
        # Scan the table
        response = table.scan()
        items = response['Items']
        
        # Handle pagination if there are more items
        while 'LastEvaluatedKey' in response:
            response = table.scan(ExclusiveStartKey=response['LastEvaluatedKey'])
            items.extend(response['Items'])
        
        # Create dictionary from items
        for item in items: 
            func_name = item.get('LambdaFuncName')
            func_value = item.get('LambdaFuncValue')
            
            if func_name and func_value:
                # Parse JSON string into dictionary
                lambda_functions[func_name] = json.loads(func_value)
        
        return lambda_functions
    
    except ClientError as e: 
        print(f"Error accessing DynamoDB: {e.response['Error']['Message']}")
        return {}
    except Exception as e:
        print(f"Unexpected error: {str(e)}")
        return {}


if __name__ == "__main__": 
    # Setup argument parser
    parser = argparse.ArgumentParser(description='Deploy Lambda functions to prod or nonprod environments')
    group = parser.add_mutually_exclusive_group(required=True)
    parser.add_argument('-d', '--dry-run', action='store_true', help='Dry run mode (no deployment)')
    group.add_argument('-n', '--nonprod', action='store_true', help='Deploy to non-production environments')
    group.add_argument('-p', '--prod', action='store_true', help='Deploy to production environments')
    parser.add_argument('-u', '--update', action='store_true', default=False, help='Update Lambda function code (default: False)')
    args = parser.parse_args()
    
    # Configuration
    TABLE_NAME = myDynamoDBTable
    REGION = myDynamoRegion
    
    # Get the dictionary
    lambdaDict = get_lambda_functions_dict(TABLE_NAME, REGION)

    PROD = args.prod
    NONPROD = args.nonprod
    UPDATE_LAMBDA = args.update

    for lambda_name, lambda_value in lambdaDict.items():
        for env_name, env_value in lambda_value.items():
            is_prod_env = "prod" in env_name.lower()
            if (PROD and is_prod_env) or (NONPROD and not is_prod_env):
                print(f"{lambda_name}, {env_name}, {env_value['region']}, {env_value['params']}")
                if not args.dry_run:
                    print("Triggering GitHub Actions workflow...")
                    runWorkflow(
                        builddir=lambda_name,
                        cftparam=env_value['params'],
                        environment=env_name,
                        update=UPDATE_LAMBDA,
                        region=env_value['region']
                    )
