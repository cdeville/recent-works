import csv
import boto3
import re
from logging_utils import setup_logging

# Initialize logger
logger = setup_logging()


def clean_tags(tags):
    """
    Clean and format tags data to be newline-separated.
    
    Each tag must contain only alphanumeric characters, underscores, and hyphens.
    Tags are converted to uppercase and duplicates are removed.
    
    Args:
        tags: String containing tags (comma, whitespace, or newline separated)
        
    Returns:
        str: Newline-separated uppercase tags string
    """
    if not tags:
        return ''
    
    # Replace commas and newlines with spaces to normalize separators
    tags = tags.replace(',', ' ').replace('\n', ' ').replace('\r', ' ')
    # Split on whitespace
    tag_list = tags.split()
    
    # Remove duplicates and filter invalid characters
    seen = set()
    unique_tags = []
    for tag in tag_list:
        # Keep only alphanumeric, underscore, and hyphen characters
        cleaned_tag = re.sub(r'[^a-zA-Z0-9_-]', '', tag)
        
        if cleaned_tag:  # Only add non-empty tags
            # Convert to uppercase
            cleaned_tag_upper = cleaned_tag.upper()
            
            # Check for duplicates (case-insensitive already since we uppercased)
            if cleaned_tag_upper not in seen:
                seen.add(cleaned_tag_upper)
                unique_tags.append(cleaned_tag_upper)
    
    # Sort alphabetically and join with spaces
    unique_tags.sort()
    return ' '.join(unique_tags)


def delete_s3_object(s3bucket, s3key):
    """
    Delete a file from S3 (only if it's a CSV file).
    
    Args:
        s3bucket: S3 bucket name
        s3key: S3 object key/path
        
    Returns:
        None
    """
    try:
        # Only delete CSV files
        if not s3key.lower().endswith('.csv'):
            logger.info(f"Skipping deletion - not a CSV file: s3://{s3bucket}/{s3key}")
            return
        
        logger.info(f"Deleting S3 object: s3://{s3bucket}/{s3key}")
        s3_client = boto3.client('s3')
        s3_client.delete_object(Bucket=s3bucket, Key=s3key)
        logger.info(f"Successfully deleted S3 object: s3://{s3bucket}/{s3key}")
    except Exception as e:
        logger.exception(f"Error deleting S3 object s3://{s3bucket}/{s3key}: {str(e)}")
        raise


def thirdparty_item_update(db_connect, db_table, s3bucket, s3path):
    """
    Process the uploaded CSV file from S3 and update thirdparty items in the database.
    
    Args:
        db_connect: MySQL database connection object
        db_table: Database table name
        s3bucket: S3 bucket name where the CSV file is located
        s3path: S3 key/path of the uploaded CSV file
        
    Returns:
        None
    """
    try:
        logger.info(f"Starting thirdparty item update - Bucket: {s3bucket}, Path: {s3path}")
        
        # Create S3 client
        s3_client = boto3.client('s3')
        
        # Get the CSV file from S3
        csv_object = s3_client.get_object(Bucket=s3bucket, Key=s3path)
        csv_content = csv_object['Body'].read().decode('utf-8')
        
        # Read CSV content
        # Read CSV content
        csv_reader = csv.DictReader(csv_content.splitlines())
        
        # Process each row in the CSV and update the database
        # Each row should contain 'ID' and 'TAGS' columns
        for row in csv_reader:
            item_id = row.get('ID')
            tags = row.get('TAGS', '')
            
            # Clean and format tags (uppercase, dedupe, validate characters)
            cleaned_tags = clean_tags(tags)
            
            logger.info(f"Updating TAGS for item ID: {item_id} with value: '{cleaned_tags}'")
            
            # Update TAGS for matching item ID with GROUPID = 12
            # GROUPID 12 = thirdparty items - this ensures we only update thirdparty items
            # and prevents accidental updates to other item groups
            update_query = f"""
                UPDATE {db_table}
                SET TAGS = %s
                WHERE ID = %s 
                AND GROUPID = '12'
            """
            cursor = db_connect.cursor()
            cursor.execute(update_query, (cleaned_tags, item_id))
            db_connect.commit()
            cursor.close()
        
        logger.info("thirdparty item update completed successfully")
        
        # Delete the processed S3 file to prevent reprocessing and keep bucket clean
        delete_s3_object(s3bucket, s3path)
        
    except Exception as e:
        logger.exception(f"Error updating thirdparty items: {str(e)}")
        raise