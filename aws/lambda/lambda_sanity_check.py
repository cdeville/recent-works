import os
import json
import boto3
import time
from datetime import datetime, timedelta
# Import structured logging setup
from logging_utils import setup_logging


"""
Lambda Sanity Check - Automated Error Detection for Lambda Functions

Purpose:
    Monitors Lambda function logs across multiple functions by scanning CloudWatch Logs
    for error messages. Uses ECR repository names as a proxy for Lambda function names
    and executes CloudWatch Logs Insights queries to detect errors within a specified
    time range.

Environment Variables:
    Required:
        - (None - function will run with defaults)
    
    Optional:
        - EXCLUDE_REPOS: Comma-separated list of patterns to exclude from scanning
        - BATCH_SIZE: Number of log groups per query (default: 50, max: 50)
        - HOURS_BACK: Number of hours of logs to analyze (default: 24)
        - MAX_QUERY_ATTEMPTS: Query timeout in seconds (default: 60)
        - SNS_TOPIC_ARN: SNS topic ARN for notifications (if omitted, no notification sent)

IAM Permissions Required:
    - ecr:DescribeRepositories
    - logs:DescribeLogGroups
    - logs:StartQuery
    - logs:GetQueryResults
    - sns:Publish (if using SNS notifications)

Trigger:
    Should be scheduled via EventBridge/CloudWatch Events (e.g., daily or hourly)
    to perform regular health checks across all Lambda functions.
"""


# Initialize logger for structured, JSON-formatted logs
logger = setup_logging()

def get_ecr_repositories(exclude_list=None):
    """
    Retrieve list of ECR repository names, optionally filtering by exclude list.
    
    Args:
        exclude_list: List of strings to exclude from repository names
        
    Returns:
        List of ECR repository names
    """
    if exclude_list is None:
        exclude_list = []
    
    ecr_client = boto3.client('ecr')
    repositories = []
    
    try:
        # Paginate through all ECR repositories
        paginator = ecr_client.get_paginator('describe_repositories')
        
        for page in paginator.paginate():
            for repo in page['repositories']:
                repo_name = repo['repositoryName']
                repositories.append(repo_name)
        
        logger.info(f"Found {len(repositories)} total ECR repositories")
        
        # Filter out excluded repositories
        if exclude_list:
            filtered_repos = [
                repo for repo in repositories 
                if not any(exclude in repo for exclude in exclude_list)
            ]
            logger.info(f"Filtered to {len(filtered_repos)} repositories after applying exclusions")
            return filtered_repos
        
        return repositories
        
    except Exception as e:
        logger.error(f"Error retrieving ECR repositories: {e}", exc_info=True)
        raise

def validate_log_groups(log_group_names):
    """
    Validate which log groups actually exist.
    
    Args:
        log_group_names: List of log group names to validate
        
    Returns:
        Tuple of (existing_log_groups, missing_log_groups)
    """
    logs_client = boto3.client('logs')
    existing = []
    missing = []
    
    for log_group in log_group_names:
        try:
            # Try to describe the log group
            response = logs_client.describe_log_groups(
                logGroupNamePrefix=log_group,
                limit=1
            )
            
            # Check if exact match exists
            if response['logGroups'] and response['logGroups'][0]['logGroupName'] == log_group:
                existing.append(log_group)
            else:
                missing.append(log_group)
                
        except Exception as e:
            logger.warning(f"Error checking log group {log_group}: {e}")
            missing.append(log_group)
    
    return existing, missing

def build_cloudwatch_query(repositories):
    """
    Build CloudWatch Logs Insights query for a batch of repositories.
    
    Args:
        repositories: List of repository names
        
    Returns:
        Query string for CloudWatch Logs Insights
    """
    
    # Build query without backticks around keywords
    query = f"""fields @timestamp, @message, @log
| filter @message like /(?i)error/
| sort @timestamp desc
| limit 1000"""
    
    return query

def execute_cloudwatch_query(query, log_group_names, start_time, end_time):
    """
    Execute a CloudWatch Logs Insights query and wait for results.
    
    Args:
        query: CloudWatch Logs Insights query string
        log_group_names: List of log group names to query
        start_time: Start time for query (epoch seconds)
        end_time: End time for query (epoch seconds)
        
    Returns:
        Query results
    """
    logs_client = boto3.client('logs')
    
    try:
        # Start the query
        response = logs_client.start_query(
            logGroupNames=log_group_names,
            startTime=start_time,
            endTime=end_time,
            queryString=query
        )
        
        query_id = response['queryId']
        logger.info(f"Started CloudWatch query: {query_id}")
        
        # Poll for query completion
        # 60 attempts with 1 second delay = 1 minute timeout
        max_attempts = int(os.environ.get('MAX_QUERY_ATTEMPTS', 60))  
        attempt = 0
        
        while attempt < max_attempts:
            attempt += 1
            time.sleep(1)  # Wait 1 second between checks
            
            result = logs_client.get_query_results(queryId=query_id)
            status = result['status']
            
            if status == 'Complete':
                logger.info(f"Query {query_id} completed with {len(result.get('results', []))} results")
                return {
                    'query_id': query_id,
                    'status': status,
                    'results': result.get('results', []),
                    'statistics': result.get('statistics', {})
                }
            elif status in ['Failed', 'Cancelled', 'Timeout']:
                logger.error(f"Query {query_id} ended with status: {status}")
                return {
                    'query_id': query_id,
                    'status': status,
                    'error': f"Query ended with status: {status}"
                }
        
        # Timeout reached
        logger.warning(f"Query {query_id} timed out after {max_attempts} seconds")
        return {
            'query_id': query_id,
            'status': 'Timeout',
            'error': f"Query timed out after {max_attempts} seconds"
        }
        
    except Exception as e:
        logger.error(f"Error executing CloudWatch query: {e}", exc_info=True)
        raise

def format_results_as_table(batch_results):
    """
    Format CloudWatch Logs Insights results as a plain text table.
    
    Args:
        batch_results: List of batch results with query results
        
    Returns:
        Plain text formatted table string
    """
    output = []
    output.append("=" * 100)
    output.append("LAMBDA SANITY CHECK RESULTS")
    output.append("=" * 100)
    output.append("")
    
    total_errors = 0
    
    for batch_result in batch_results:
        batch_num = batch_result['batch_number']
        results = batch_result['query_result'].get('results', [])
        error_count = len(results)
        total_errors += error_count
        
        # Batch header
        output.append(f"\n{'='*100}")
        output.append(f"BATCH {batch_num}")
        output.append(f"{'='*100}")
        output.append(f"Repositories: {len(batch_result['repositories'])}")
        output.append(f"Errors Found: {error_count}")
        output.append("")
        
        if error_count > 0:
            # Table header
            output.append(f"{'Timestamp':<25} | {'Log Group':<40} | {'Message'}")
            output.append(f"{'-'*25}-+-{'-'*40}-+-{'-'*30}")
            
            for result in results:
                # Extract fields from CloudWatch result
                timestamp = ""
                log = ""
                message = ""
                
                for field in result:
                    if field['field'] == '@timestamp':
                        timestamp = field['value']
                    elif field['field'] == '@log':
                        log = field['value']
                    elif field['field'] == '@message':
                        message = field['value']
                
                # Truncate long values for readability
                log_short = log[-40:] if len(log) > 40 else log
                message_short = message[:80] + "..." if len(message) > 80 else message
                
                # Add row to table
                output.append(f"{timestamp:<25} | {log_short:<40} | {message_short}")
            
            output.append("")
        else:
            output.append("No errors found in this batch.")
            output.append("")
    
    # Summary
    output.append(f"\n{'='*100}")
    output.append("SUMMARY")
    output.append(f"{'='*100}")
    output.append(f"Total Errors Found: {total_errors}")
    output.append(f"{'='*100}")
    
    return "\n".join(output)

def send_sns_notification(subject, message, sns_topic_arn):
    """
    Send SNS notification with plain text message.
    
    Args:
        subject: Email subject line
        message: Plain text message body
        sns_topic_arn: ARN of the SNS topic
    """
    sns_client = boto3.client('sns')
    
    try:
        response = sns_client.publish(
            TopicArn=sns_topic_arn,
            Subject=subject,
            Message=message
        )
        logger.info(f"SNS notification sent successfully. MessageId: {response['MessageId']}")
        return response['MessageId']
    except Exception as e:
        logger.error(f"Error sending SNS notification: {e}", exc_info=True)
        raise

def handler(event, context):
    """
    Lambda Sanity Check Handler
    
    Retrieves ECR repository names (which match Lambda function names) 
    and performs sanity checks on them.
    """
    try:
        # Log the incoming event
        logger.info("Lambda Sanity Check invoked", extra={"event": event})
        
        # Get exclude list from environment variable (comma-separated)
        exclude_env = os.environ.get('EXCLUDE_REPOS', '')
        exclude_list = [item.strip() for item in exclude_env.split(',') if item.strip()]
        
        if exclude_list:
            logger.info(f"Exclude list: {exclude_list}")
        
        # Get ECR repositories
        repositories = get_ecr_repositories(exclude_list)
        total_repos = len(repositories)
        
        # Split repositories into batches of 50 if greater than 50
        # CloudWatch Log Insights has a 50 Log Group limit
        batch_size = int(os.environ.get('BATCH_SIZE', 50))
        batches = []
        
        if total_repos > batch_size:
            logger.info(f"Splitting {total_repos} repositories into batches of {batch_size}")
            for i in range(0, total_repos, batch_size):
                batch = repositories[i:i + batch_size]
                batches.append(batch)
            logger.info(f"Created {len(batches)} batches")
        else:
            # If 50 or fewer, keep as single batch
            batches.append(repositories)
        
        # Get time range for CloudWatch query (default: last 24 hours)
        hours_back = int(os.environ.get('HOURS_BACK', 24))
        end_time = datetime.now()
        start_time = end_time - timedelta(hours=hours_back)
        
        # Convert to epoch seconds
        start_epoch = int(start_time.timestamp())
        end_epoch = int(end_time.timestamp())
        
        logger.info(f"Querying CloudWatch logs from {start_time} to {end_time} ({hours_back} hours)")
        
        # Execute CloudWatch queries for each batch
        batch_results = []
        for idx, batch in enumerate(batches):
            logger.info(f"Processing batch {idx + 1}/{len(batches)} with {len(batch)} repositories")
            
            # Convert repository names to log group names
            log_group_names = [f'/aws/lambda/{repo}' for repo in batch]
            
            # Validate which log groups exist
            existing_log_groups, missing_log_groups = validate_log_groups(log_group_names)
            
            if missing_log_groups:
                logger.warning(f"Batch {idx + 1}: {len(missing_log_groups)} log group(s) do not exist: {missing_log_groups}")
            
            if not existing_log_groups:
                logger.warning(f"Batch {idx + 1}: No valid log groups found, skipping query")
                batch_results.append({
                    'batch_number': idx + 1,
                    'repository_count': len(batch),
                    'repositories': batch,
                    'existing_log_groups': [],
                    'missing_log_groups': missing_log_groups,
                    'query_result': {
                        'status': 'Skipped',
                        'message': 'No valid log groups found'
                    }
                })
                continue
            
            logger.info(f"Batch {idx + 1}: Querying {len(existing_log_groups)} existing log group(s)")
            
            # Build query for this batch
            query = build_cloudwatch_query(batch)
            
            # Execute query only on existing log groups
            result = execute_cloudwatch_query(query, existing_log_groups, start_epoch, end_epoch)
            
            batch_results.append({
                'batch_number': idx + 1,
                'repository_count': len(batch),
                'repositories': batch,
                'existing_log_groups': existing_log_groups,
                'missing_log_groups': missing_log_groups,
                'query_result': result
            })
        
        # Count total errors found
        total_errors = sum(
            len(batch_result['query_result'].get('results', [])) 
            for batch_result in batch_results
        )
        
        # Build response
        response = {
            'status': 'success',
            'total_repositories': total_repos,
            'batch_count': len(batches),
            'batch_size': batch_size,
            'time_range': {
                'start': start_time.isoformat(),
                'end': end_time.isoformat(),
                'hours_back': hours_back
            },
            'total_errors_found': total_errors,
            'batch_results': batch_results,
            'excluded_patterns': exclude_list
        }
        
        logger.info(f"Sanity check completed. Found {total_errors} errors across {total_repos} repositories in {len(batches)} batch(es).")
        
        # Send SNS notification if topic ARN is configured
        sns_topic_arn = os.environ.get('SNS_TOPIC_ARN')
        if sns_topic_arn:
            logger.info(f"SNS topic configured: {sns_topic_arn}")
            
            # Format results as plain text table
            text_message = format_results_as_table(batch_results)
            
            # Create subject line
            subject = f"Lambda Sanity Check: {total_errors} Error(s) Found"
            if total_errors == 0:
                subject = "Lambda Sanity Check: No Errors Found ✓"
            
            # Send notification
            message_id = send_sns_notification(subject, text_message, sns_topic_arn)
            response['sns_message_id'] = message_id
            logger.info(f"SNS notification sent with MessageId: {message_id}")
        else:
            logger.info("SNS_TOPIC_ARN not configured, skipping notification")
        
        return {
            'statusCode': 200,
            'body': json.dumps(response, indent=2, default=str)
        }
        
    except Exception as e:
        # Log any error with stack trace
        logger.error(f"Error during sanity check: {e}", exc_info=True)
        return {
            'statusCode': 500,
            'body': json.dumps({
                'status': 'error',
                'message': f'Error during sanity check: {str(e)}'
            }, indent=2)
        }