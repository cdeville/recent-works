import boto3
import json
import os
import requests
from botocore.exceptions import ClientError

"""
AWS WAF IP Set Updater - Lambda Function

Purpose:
    Automatically updates an AWS WAF IP Set with current Amazon IP address ranges.
    This Lambda function downloads the latest Amazon IP ranges and updates a 
    specified WAF IP Set to keep it current.

Required Environment Variables:
    - ERROR_SNS_TOPIC_ARN: (Optional) SNS topic ARN for error notifications
    - MAX_IPS: Maximum number of IPs allowed in the IP set (WAF limit)
    - WAF_REGION: AWS region where the WAF IP set is located
    - IP_SET_NAME: Name of the WAF IP set to update
    - AWS_URL: URL to download Amazon IP ranges (typically https://ip-ranges.amazonaws.com/ip-ranges.json)

IAM Permissions Required:
    - wafv2:ListIPSets
    - wafv2:GetIPSet
    - wafv2:UpdateIPSet
    - sns:Publish (if using error notifications)

Trigger:
    Should be scheduled via EventBridge/CloudWatch Events (e.g., daily or when AWS publishes new IP ranges)
"""

# set env vars
ERROR_TOPIC = os.environ.get("ERROR_SNS_TOPIC_ARN")
MAX_IPS_PER_IPSET = int(os.environ.get("MAX_IPS"))
WAF_REGION = os.environ.get("WAF_REGION")
IP_SET_NAME = os.environ.get("IP_SET_NAME")
URL = os.environ.get("AWS_URL")
SCOPE = "REGIONAL"  # Use "CLOUDFRONT" for global

# configure aws services
waf = boto3.client("wafv2", region_name=WAF_REGION)
sns = boto3.client("sns", region_name=WAF_REGION)

def handler(event, context):
    try:
        # Step 1: Download Amazon IP ranges
        response = requests.get(URL)
        response.raise_for_status()
        ip_data = response.json()

        # Step 2: Filter IP prefixes (e.g., service == "AMAZON")
        new_ip_addresses = [
            entry["ip_prefix"]
            for entry in ip_data.get("prefixes", [])
            if entry["service"] == "AMAZON"
        ]
        if len(new_ip_addresses) > MAX_IPS_PER_IPSET:
            raise Exception(f"Too many IPs to fit in WAF IP set: {len(new_ip_addresses)}")

        # Step 3: Get existing IP set metadata
        ip_sets = waf.list_ip_sets(Scope=SCOPE, Limit=100)["IPSets"]
        ip_set = next((s for s in ip_sets if s["Name"] == IP_SET_NAME), None)
        if not ip_set:
            raise Exception(f"IP set '{IP_SET_NAME}' not found.")

        ip_set_details = waf.get_ip_set(Name=IP_SET_NAME, Scope=SCOPE, Id=ip_set["Id"])
        lock_token = ip_set_details["LockToken"]

        # Step 4: Update the IP set
        waf.update_ip_set(
            Name=IP_SET_NAME,
            Scope=SCOPE,
            Id=ip_set["Id"],
            Addresses=new_ip_addresses,
            LockToken=lock_token,
        )

        print(f"Successfully updated {IP_SET_NAME} with {len(new_ip_addresses)} addresses.")
        return {
            "statusCode": 200,
            "body": f"Successfully updated {IP_SET_NAME} with {len(new_ip_addresses)} addresses."
        }

    except Exception as e:
        err_msg = f"Error updating IP set: {str(e)}"
        print(err_msg)

        # send to SNS if configured
        if ERROR_TOPIC:
            try:
                sns.publish(
                    TopicArn=ERROR_TOPIC,
                    Subject=f"Lambda {context.function_name} failed",
                    Message=json.dumps({
                        "error": err_msg,
                        "function": context.function_name,
                        "requestId": context.aws_request_id,
                        "event": event
                    })
                )
            except ClientError as sns_err:
                # if SNS itself fails, log but continue
                print(f"Failed to publish error to SNS: {sns_err}")

        # re‑raise so that Lambda signals a failure (optional)
        raise