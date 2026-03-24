import csv
import io
import boto3
from logging_utils import setup_logging

# Initialize logger
logger = setup_logging()


def query_thirdparty_items(db_connect, db_table):
    """
    Query database for all thirdparty items.
    
    Args:
        db_connect: MySQL database connection object
        db_table: Database table name
        
    Returns:
        list: Query results as list of tuples
    """
    cursor = db_connect.cursor()
    try:
        query = f"SELECT ID, NAME, DESCRIPTION, TAGS FROM {db_table} WHERE GROUPID = 12"
        logger.info(f"Executing query: {query}")
        cursor.execute(query)
        
        results = cursor.fetchall()
        logger.info(f"Query returned {len(results)} rows")
        return results
    except Exception as e:
        logger.error(f"Database query failed: {str(e)}")
        raise
    finally:
        cursor.close()


def create_csv_content(data):
    """
    Convert query results to CSV format.
    
    Args:
        data: List of tuples containing row data
        
    Returns:
        str: CSV formatted string
    """
    csv_buffer = io.StringIO()
    csv_writer = csv.writer(csv_buffer)
    
    # Write header
    csv_writer.writerow(['ID', 'NAME', 'DESCRIPTION', 'TAGS'])
    
    # Write data rows
    csv_writer.writerows(data)
    
    csv_content = csv_buffer.getvalue()
    csv_buffer.close()
    
    return csv_content


def construct_s3_key(s3path):
    """
    Construct S3 key with proper path formatting.
    
    Args:
        s3path: S3 path/prefix for the file
        
    Returns:
        str: Properly formatted S3 key
    """
    # Ensure path ends with / if it's not empty to avoid malformed paths
    if s3path and not s3path.endswith('/'):
        s3path = s3path + '/'
    # Use fixed filename so users can always find the latest sample at same location
    return f"{s3path}thirdparty_item_sample.csv"


def upload_to_s3(s3bucket, s3_key, content):
    """
    Upload CSV content to S3.
    
    Args:
        s3bucket: S3 bucket name
        s3_key: S3 key (path + filename)
        content: CSV content as string
        
    Returns:
        str: S3 URI of uploaded file
    """
    try:
        logger.info(f"Uploading CSV to s3://{s3bucket}/{s3_key}")
        s3_client = boto3.client('s3')
        s3_client.put_object(
            Bucket=s3bucket,
            Key=s3_key,
            Body=content.encode('utf-8'),
            ContentType='text/csv'
        )
        
        s3_uri = f"s3://{s3bucket}/{s3_key}"
        logger.info(f"Successfully uploaded sample file to {s3_uri}")
        return s3_uri
    except Exception as e:
        logger.error(f"S3 upload failed: {str(e)}")
        raise


def create_sample(db_connect, db_table, s3bucket, s3path):
    """
    Create a sample CSV file of thirdparty items and upload to S3.
    
    Args:
        db_connect: MySQL database connection object
        db_table: Database table name
        s3bucket: S3 bucket name for upload
        s3path: S3 path/prefix for the file
        
    Returns:
        str: S3 URI of uploaded file
    """
    try:
        logger.info(f"Creating thirdparty item sample - Bucket: {s3bucket}, Path: {s3path}")
        
        # Execute query to get all thirdparty items (GROUPID = 12)
        results = query_thirdparty_items(db_connect, db_table)
        
        # Convert to CSV format
        csv_content = create_csv_content(results)
        
        # Construct S3 key
        s3_key = construct_s3_key(s3path)
        
        # Upload to S3 and return URI
        return upload_to_s3(s3bucket, s3_key, csv_content)
        
    except Exception as e:
        logger.exception(f"Error creating sample file: {str(e)}")
        raise