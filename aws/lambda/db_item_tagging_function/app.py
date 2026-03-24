# Standard Libraries
import json
import os

# Item Tagging Libraries
from item_update import thirdparty_item_update
from sample import create_sample

# Shared Libraries
from shared_libs import (
    connect_mysql
)
from logging_utils import setup_logging


"""
AWS Lambda Function for Database Item Tagging

Purpose:
    Provides a self-service workflow for business users to manage "thirdparty" item tags 
    in the database without requiring direct database access or SQL knowledge. Users 
    download a CSV sample, edit tags in Excel/Sheets, and upload to trigger updates.

Operations:
    1. Sample Generation (EventBridge scheduled): Creates CSV export of current thirdparty items
    2. CSV Processing (S3 upload trigger): Updates database tags from uploaded CSV
    3. Post-Update Sample: Regenerates fresh CSV after updates for verification
"""


# Initialize logger for structured, JSON-formatted logs
logger = setup_logging()


def get_database_connection():
    """
    Get database connection based on environment (local dev vs AWS).
    
    The connection uses AWS Secrets Manager to retrieve database credentials.
    In LOCAL_DEV mode, connects to a local database via localhost.
    In AWS mode, connects to RDS using VPC networking.
    
    Returns:
        MySQL connection object
    """
    # Check if running in local development mode
    local_dev = os.getenv('LOCAL_DEV', 'false').lower() == 'true'
    # Secret name containing database connection credentials
    db_db_secret_name = os.getenv('DB_SECRET_NAME')

    if local_dev:
        logger.info("LOCAL_DEV mode: Connecting to localhost database")
        # Local dev uses SSH tunnel or local MySQL instance
        connection = connect_mysql(
            db_db_secret_name,
            host='127.0.0.1'
        )
    else:
        logger.info("AWS mode: Connecting to RDS database")
        # AWS mode connects via VPC to RDS endpoint from secrets
        connection = connect_mysql(
            db_db_secret_name
        )
    
    logger.info("Database connection established successfully")
    return connection

def lambda_handler(event, context):
    """
    AWS Lambda handler for thirdparty item tagging operations.
    
    Supports two trigger types:
    1. EventBridge Scheduled Event: Generates sample CSV of thirdparty items (GROUPID=12)
    2. S3 Event: Processes uploaded CSV to update item tags in database
    
    Args:
        event: Event data containing either:
               - EventBridge: {'Trigger': 'create_sample', 'DBTable': '...', 'S3Bucket': '...', 'S3Path': '...'}
               - S3: {'Records': [{'s3': {'bucket': {'name': '...'}, 'object': {'key': '...'}}}]}
        context: Lambda runtime information and metadata
    
    Environment Variables:
        DBTable: Database table name (e.g., 'dbname.item')
        DB_SECRET_NAME: AWS Secrets Manager secret containing DB credentials
        S3PATH: Default S3 path for sample file output
        LOCAL_DEV: 'true' for local development mode
    """
    try:
        logger.info(f"Lambda function invoked with event: {json.dumps(event)}")
        
        # Check if this is an EventBridge scheduled trigger (has 'Trigger' key)
        if 'Trigger' in event:
            # Get database table name from environment (set in CloudFormation template)
            db_table = os.getenv('DBTable')
            
            # Extract event parameters for the scheduled action
            trigger_type = event.get('Trigger')  # e.g., 'create_sample'
            s3bucket = event.get('S3Bucket')     # Target S3 bucket for output
            s3path = event.get('S3Path')         # Target S3 path/prefix for output
            logger.info(f"Processing EventBridge trigger: {trigger_type}")
            
            if trigger_type == 'create_sample':
                # Generate a sample CSV file with thirdparty items (GROUPID=12) for download/review
                logger.info("Executing create_sample script")
                db_connect = get_database_connection()
                create_sample(db_connect, db_table, s3bucket, s3path)
            else:
                # Log unrecognized trigger types (should not happen with proper EventBridge config)
                logger.warning(f"Unknown trigger type: {trigger_type}")
        
        # Check if this is an S3 event (triggered by CSV file upload)
        elif 'Records' in event:
            logger.info("Processing S3 event")
            # Get database table name from environment (set in CloudFormation template)
            db_table = os.getenv('DBTable')
            
            # Process each S3 record (typically one, but batch processing supported)
            for record in event.get('Records', []):
                # Extract S3 bucket and object key from the event
                s3_info = record.get('s3', {})
                s3bucket = s3_info.get('bucket', {}).get('name')
                s3path = s3_info.get('object', {}).get('key')  # Full path to uploaded CSV
                s3samplepath = os.getenv('S3PATH')  # Default path for sample output
                
                db_connect = get_database_connection()
                logger.info(f"Processing S3 object - Bucket: {s3bucket}, Key: {s3path}")
                
                # Update database with tags from uploaded CSV, then delete the processed file
                thirdparty_item_update(db_connect, db_table, s3bucket, s3path)
                
                # Generate fresh sample file after updates for user reference
                logger.info("Executing create_sample script")
                create_sample(db_connect, db_table, s3bucket, s3samplepath)
        
        else:
            logger.warning(f"Unknown event type - no 'Trigger' or 'Records' found in event")
        
        logger.info("Lambda function completed successfully")
        
    except Exception as e:
        logger.exception(f"Error processing event: {str(e)}")
        raise