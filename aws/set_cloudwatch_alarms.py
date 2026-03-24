#!/usr/bin/env python3

#Python Build-In Modules
import argparse
import logging
import re

# Third-Party Modules
import boto3
from botocore.exceptions import ClientError

# Setup logging
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


def get_alb_full_name(arn):
    match = re.search(r':loadbalancer/(app/[^/]+/[^/]+)', arn)
    return match.group(1) if match else None

def get_tg_full_name(arn):
    match = re.search(r':targetgroup/([^/]+/[^/]+)', arn)
    return match.group(1) if match else None


def create_alarm(
    cloudwatch,
    alarm_name: str,
    namespace: str,
    metric_name: str,
    dimensions: list,
    threshold: float,
    comparison: str,
    period: int,
    evaluation_periods: int,
    sns_arn: str,
    statistic: str = "Average",
    unit: str = None,
    treat_missing_data: str = "missing"
):
    kwargs = {
        "AlarmName": alarm_name,
        "Namespace": namespace,
        "MetricName": metric_name,
        "Dimensions": dimensions,
        "Statistic": statistic,
        "Period": period,
        "EvaluationPeriods": evaluation_periods,
        "Threshold": threshold,
        "ComparisonOperator": comparison,
        "AlarmActions": [sns_arn],
        "ActionsEnabled": True,
        "TreatMissingData": treat_missing_data
    }
    if unit:
        kwargs["Unit"] = unit

    cloudwatch.put_metric_alarm(**kwargs)
    logger.info(f"Created alarm: {alarm_name}")


def main():
    parser = argparse.ArgumentParser(description="Create CloudWatch Alarms")
    parser.add_argument("--profile", required=True, help="AWS profile name")
    parser.add_argument("--region", required=True, help="AWS region")
    parser.add_argument("--sns-arn", required=True, help="SNS topic ARN for alarm actions")

    args = parser.parse_args()

    # Boto3 session
    session = boto3.Session(profile_name=args.profile, region_name=args.region)
    cloudwatch = session.client('cloudwatch')
    elbv2 = session.client('elbv2')
    rds = session.client('rds')

    try:
        loadbalancers = elbv2.describe_load_balancers()['LoadBalancers']
        targetgroups = elbv2.describe_target_groups()['TargetGroups']
        db_instances = rds.describe_db_instances()["DBInstances"]
    except ClientError as e:
        logger.error(f"AWS API error: {e}")
        return

    # ALB Alarms
    logger.info("Setting up Elastic Load Balancer alarms...")
    internal_lbs = []
    for lb in loadbalancers:
        lb_arn_suffix = get_alb_full_name(lb['LoadBalancerArn'])
        lb_name = lb['LoadBalancerName']
        # Add any internal LoadBalancers to our internal_lbs list
        try:
            if lb.get('Scheme') == "internal":
                internal_lbs.append(lb_arn_suffix)
            # Give internal ALBs an identifying name
            if lb_arn_suffix in internal_lbs:
                lb_name = f"{lb_name}-Internal"
        except:
            logger.warning(f"Error tracking internal ALB: {lb_name}")

        for metric_def in [
            ("5XX-High", "HTTPCode_ELB_5XX_Count", 10, 60, 3, "Sum"), # 10 5XX count
            ("Target5XX-High", "HTTPCode_Target_5XX_Count", 10, 60, 3, "Sum"), # 10 5XX count
            ("TargetLatency-High", "TargetResponseTime", 20.0, 60, 3, "Average"), # 1.0 secs
            ("RequestCount-Spike", "RequestCount", 10000, 60, 3, "Sum") # 10k requests
        ]:
            try:
                alarm_suffix, metric_name, threshold, period, eval_period, stat = metric_def
                alarm_name = f"ALB-{lb_name}-{alarm_suffix}"
                logger.info(f'Creating Alarm: {alarm_name}')
                create_alarm(
                    cloudwatch=cloudwatch,
                    alarm_name=alarm_name,
                    namespace="AWS/ApplicationELB",
                    metric_name=metric_name,
                    dimensions=[{"Name": "LoadBalancer", "Value": lb_arn_suffix}],
                    threshold=threshold,
                    comparison="GreaterThanThreshold",
                    period=period,
                    evaluation_periods=eval_period,
                    sns_arn=args.sns_arn,
                    statistic=stat,
                    treat_missing_data="notBreaching"
                )
            except ClientError as e:
                logger.error(f"Error creating {metric_name} alarm for {lb_name}: {e}")

    # Target Group Alarms
    logger.info("Setting up Target Group alarms...")
    for tg in targetgroups:
        lb_arn_suffix=""
        tg_arn_suffix = get_tg_full_name(tg['TargetGroupArn'])
        tg_name = tg['TargetGroupName']
        lb_arn_suffix = get_alb_full_name(tg['LoadBalancerArns'][0]) if tg['LoadBalancerArns'] else None
        try:
            # Label Internal TGs appropriately
            if lb_arn_suffix in internal_lbs:
                tg_name = f"{tg_name}-Internal"
        except:
            logger.warning(f"Error tracking internal Target Group: {tg_name}")

        # Skip Target Groups not attached to an ALB    
        if not lb_arn_suffix:
            logger.warning(f"Skipping target group {tg_name} with no attached ALB")
            continue

        try:
            alarm_name = f"TG-{tg_name}-UnhealthyHosts"
            logger.info(f'Creating Alarm: {alarm_name}')
            create_alarm(
                cloudwatch=cloudwatch,
                alarm_name=alarm_name,
                namespace="AWS/ApplicationELB",
                metric_name="UnhealthyHostCount",
                dimensions=[
                    {"Name": "TargetGroup", "Value": tg_arn_suffix},
                    {"Name": "LoadBalancer", "Value": lb_arn_suffix}
                ],
                threshold=1,
                comparison="GreaterThanThreshold",
                period=60,
                evaluation_periods=1,
                sns_arn=args.sns_arn,
                statistic="Average",
                treat_missing_data="notBreaching"
            )
        except ClientError as e:
            logger.error(f"Error creating UnhealthyHostCount alarm for {tg_name}: {e}")


    # RDS Alarms
    for db in db_instances:
        db_id = db["DBInstanceIdentifier"]

        for metric_def in [
            ("CPUUtilization-High", "CPUUtilization", 85, 60, 5, "Average"), # 85%
            ("FreeStorage-Low", "FreeStorageSpace", 30 * 1024**3, 300, 1, "Minimum"),  # 10 GB
            ("Connections-Spike", "DatabaseConnections", 25, 60, 3, "Average"), # 25 connections
            ("ReadLatency-High", "ReadLatency", 0.02, 60, 3, "Average"),  # 20 ms
            ("WriteLatency-High", "WriteLatency", 0.02, 60, 3, "Average"), # 20 ms
            ("FreeableMemory-Low", "FreeableMemory", 500 * 1024**2, 300, 1, "Minimum")  # 500 MB
        ]:
            try:
                alarm_suffix, metric_name, threshold, period, eval_period, stat = metric_def
                alarm_name = f"RDS-{db_id}-{alarm_suffix}"
                logger.info(f"Creating Alarm: {alarm_name}")
                create_alarm(
                    cloudwatch=cloudwatch,
                    alarm_name=alarm_name,
                    namespace="AWS/RDS",
                    metric_name=metric_name,
                    dimensions=[{"Name": "DBInstanceIdentifier", "Value": db_id}],
                    threshold=threshold,
                    comparison="GreaterThanThreshold" if "Low" not in alarm_suffix else "LessThanThreshold",
                    period=period,
                    evaluation_periods=eval_period,
                    sns_arn=args.sns_arn,
                    statistic=stat,
                    treat_missing_data="notBreaching"
                )
            except ClientError as e:
                logger.error(f"Error creating {metric_name} alarm for {db_id}: {e}")

if __name__ == "__main__":
    main()
