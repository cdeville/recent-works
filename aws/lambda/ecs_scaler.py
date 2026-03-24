# Standard libraries
import os

# Third-Party Libaries
import boto3
from botocore.exceptions import ClientError

# Shared Libraries
from logging_utils import setup_logging
from shared_libs import get_ssm_parameter

logger = setup_logging()


# Function to update the ECS desired count to MIN or MAX values
def update_ecs_desired_count(
    cluster_name: str,
    service_name: str,
    desired_count: int,
) -> dict:
    """
    Update the desired count for an ECS service.

    :param cluster_name:   name or ARN of the ECS cluster
    :param service_name:   name or ARN of the ECS service
    :param desired_count:  new desired task count
    :returns:              response dict from ECS update_service API
    :raises ClientError:   on AWS API failure
    """
    ecs = boto3.client('ecs')

    try:
        response = ecs.update_service(
            cluster=cluster_name,
            service=service_name,
            desiredCount=desired_count
        )
        logger.info(
            f"Updated ECS service {service_name} in cluster {cluster_name} to desired count {desired_count}"
        )
        return response
    except ClientError as e:
        logger.error(
            f"Failed to update ECS service {service_name}: {e}"
        )
        raise

# Standard AWS Handler Function
def handler(event, context):
    # Print event output for debugging
    logger.info(event)

    # Get our ECS cluster & service names and our min/max values
    try:
        logger.info("Getting ECS Info From SSM Parameter Store")
        # Import ECS Cluster & Service Name Parameter Store Names
        CLUSTER_NAME_PARAM = os.getenv("CLUSTER_NAME_PARAM")
        SERVICE_NAME_PARAM = os.getenv("SERVICE_NAME_PARAM")
        MIN_VALUE = int(os.getenv("MIN_COUNT"))
        MAX_VALUE = int(os.getenv("MAX_COUNT"))
        CLUSTER_NAME = get_ssm_parameter(CLUSTER_NAME_PARAM)
        SERVICE_NAME = get_ssm_parameter(SERVICE_NAME_PARAM)
    except ClientError as e:
        logger.error(f"Import Error: {e}")
        raise
    
    # check our event to determine our scaling plan
    # Perform "scaling" action - event key "scaling", event value "up" or "down"
    try:
        match(event['scaling']):

            # If "scaling" = "up" then set DESIRED_COUNT to MAX_VALUE
            case 'up':
                logger.info(f"ACTION: Scaling UP {CLUSTER_NAME}.{SERVICE_NAME} to {MAX_VALUE}")
                DESIRED_COUNT=MAX_VALUE
            
            # If "scaling" = "down" then set DESIRED_COUNT to MIN_VALUE
            case 'down':
                logger.info(f"ACTION: Scaling DOWN {CLUSTER_NAME}.{SERVICE_NAME} to {MIN_VALUE}")
                DESIRED_COUNT=MIN_VALUE
            
            # Account for any other unexpected event actions
            case _:
                logger.error(f"Unknown scaling action: {event['scaling']}")
                raise
    except KeyError:
        logger.error('"scaling" key is missing from the lambda event')
        raise

    # Run the update_ecs_desired_count function to scale our service appropriately
    try:
        response = update_ecs_desired_count(
            cluster_name=CLUSTER_NAME,
            service_name=SERVICE_NAME,
            desired_count=DESIRED_COUNT
        )
        logger.debug(response)
    except ClientError as e:
        logger.error(f"Update ECS Desired Count Failed: {e}")