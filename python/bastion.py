#!/usr/bin/env python3

import argparse
import boto3
import botocore.exceptions
import re
import subprocess
import sys


'''
This script is setup to simplify using SSM to connect to our AWS Bastion hosts shell 
as well as to setup port forwarding to access databases, web services, etc

# You can create shortcuts in .bashrc or .zshrc like so:
##################################################
# Custom Aliases & Functions
alias bastion='~/bin/bastion.py'
alias s-dev='~/bin/bastion.py -s -p devprofile'
alias f-dev='~/bin/bastion.py -f -F db-dev-001.xxxxxxxxxxxxxxx.us-east-2.rds.amazonaws.com -p devprofile'
awshell() {
    ~/bin/bastion.py -s -p "$1"
}
##################################################
'''

def aws_sso_login(org="awsorg"):
    # Runs the AWS SSO login command
    try:
        subprocess.run(["aws", "sso", "login", "--sso-session", org], check=True)
    except subprocess.CalledProcessError as e:
        print(f"Failed to log in: {e}")
        raise

def valid_port(value):
    # Custom type function to validate the port number
    try:
        port = int(value)
    except ValueError:
        raise argparse.ArgumentTypeError(f"{value} is not a valid integer port.")
    if port < 0 or port > 65535:
        raise argparse.ArgumentTypeError(f"{port} is an invalid port number, must be between 0 and 65535.")
    return port


def perform_boto3_operation(myProfile, org="awsorg"):
    #  Validate aws boto operations are working (SSO, etc)
    session = boto3.Session(profile_name=myProfile)
    client = session.client("sts")  # Example: Using STS to get caller identity

    attempt = 0
    max_attempts = 2  # First try, then retry after login

    while attempt < max_attempts:
        try:
            response = client.get_caller_identity()
            return response  # Successful response
        except:
            if attempt == 0:  # Only retry once
                print("Token expired. Attempting to refresh SSO session...")
                aws_sso_login(org)
                attempt += 1
            else:
                raise  # If already retried, re-raise the error


def is_valid_instance_id(instance_id):
    """Validate that a string matches the EC2 instance ID format (i- followed by 17 alphanumeric characters)"""
    return bool(re.match(r'^i-[a-z0-9]{17}$', instance_id))


def get_host_instance_id(myProfile, remote_name):
    # If remote_name is already an instance ID, return it directly
    if is_valid_instance_id(remote_name):
        return remote_name
    
    # Create a boto3 session using the specified AWS profile
    session = boto3.Session(profile_name=myProfile)
    ec2 = session.client("ec2")

    try:
        # Call describe_instances with filters for tag:Name and running state
        response = ec2.describe_instances(
            Filters=[
                {
                    "Name": "tag:Name",
                    "Values": [remote_name]
                },
                {
                    "Name": "instance-state-name",
                    "Values": ["running"]
                }
            ]
        )
    except botocore.exceptions.ClientError as e:
        error_code = e.response.get('Error', {}).get('Code', 'Unknown')
        error_message = e.response.get('Error', {}).get('Message', str(e))
        sys.exit(f"ERROR: AWS API call failed ({error_code}): {error_message}")
    except Exception as e:
        sys.exit(f"ERROR: Failed to query EC2 instances: {e}")
    
    # Extract instance IDs from the response
    instance_ids = []
    for reservation in response.get("Reservations", []):
        for instance in reservation.get("Instances", []):
            instance_ids.append(instance.get("InstanceId"))

    if len(instance_ids) > 1:
        sys.exit(f"ERROR: More than one instance with name: {remote_name}; try using the instance ID instead. Found instances: {instance_ids}")
    if len(instance_ids) == 0:
        sys.exit(f"ERROR: No running instances found with name: {remote_name}")
        
    instance_id = instance_ids[0]
    
    # Validate the instance ID format before returning
    if not is_valid_instance_id(instance_id):
        sys.exit(f"ERROR: AWS returned invalid instance ID format: {instance_id}")
    
    return instance_id


def start_port_forwarding_with_cli(myProfile, target, target_address, local_port, source_port):
    # Using the AWS CLI because boto3 doesn't maintain the tunnel
    command = [
        "aws", "ssm", "start-session",
        "--target", target,
        "--document-name", "AWS-StartPortForwardingSessionToRemoteHost",
        "--parameters", f"host={target_address},portNumber={source_port},localPortNumber={local_port}",
        "--profile", myProfile
    ]
    subprocess.run(command)


def start_interactive_shell(myProfile, target):
    # Using the AWS CLI because boto3 doesn't maintain the tunnel
    command = [
        "aws", "ssm", "start-session",
        "--target", target,
        "--profile", myProfile
    ]
    subprocess.run(command)


def main():
    parser = argparse.ArgumentParser(
        description="A CLI tool that accepts either shell forward mode along with optional port and AWS profile settings."
    )

    # Create a mutually exclusive group requiring exactly one of --shell or --db
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--shell", "-s",
        action="store_true",
        help="Enable shell mode"
    )
    group.add_argument(
        "--forward", "-f",
        action="store_true",
        help="Enable port forwarding mode"
    )

    # Optional EC2 remote host name
    parser.add_argument(
        "--host", "-H",
        type=str,
        default="bastion-host-ephemeral",
        help="Remote host to connect to"
    )

    # Optional RDS remote host name prefix
    parser.add_argument(
        "--forwardhost", "-F",
        type=str,
        help="Remote host or IP address to forward traffic from"
    )

    # Optional port argument with validation; default is 3306
    parser.add_argument(
        "--port", "-P",
        type=valid_port,
        default=3306,
        help="Local port number to forward RDS traffic to (default: 3306, valid range: 0-65535)"
    )

    # Optional port argument with validation; default is 3306
    parser.add_argument(
        "--sourceport", "-S",
        type=valid_port,
        default=3306,
        help="Remote RDS port number where traffic is coming from (default: 3306, valid range: 0-65535)"
    )

    # Optional AWS profile name
    parser.add_argument(
        "--profile", "-p",
        type=str,
        required=True,
        help="AWS profile name"
    )

    # Optional AWS SSO organization name
    parser.add_argument(
        "--org", "-o",
        type=str,
        default="awsorg",
        help="AWS SSO session/organization name (default: awsorg)"
    )

    args = parser.parse_args()

    # Validate that --forwardhost is provided when using --forward mode
    if args.forward and not args.forwardhost:
        parser.error("--forwardhost (-F) is required when using --forward mode")

    # Validate SSO Auth
    try:
        result = perform_boto3_operation(args.profile, args.org)
        print("  Assumed Role:", result['Arn'])
    except Exception as e:
        print("AWS SSO Auth Failed:", e)
        sys.exit(1)

    # start SSM session, either SHELL or PORT FORWARDING mode
    if args.shell:
        print(f"  Shell mode: {args.shell}")
        print(f"  Host: {args.host}")
        remote_id = get_host_instance_id(args.profile, args.host)
        print(f"  Remote EC2 Instance ID: {remote_id}")
        start_interactive_shell(args.profile, remote_id)
    elif args.forward:
        print(f"  Port Forwarding mode: {args.forward}")
        print(f"  Forward Host: {args.forwardhost}")
        print(f"  Local Port: {args.port}")
        print(f"  Source Port: {args.sourceport}")
        bastion_id = get_host_instance_id(args.profile, args.host)
        start_port_forwarding_with_cli(args.profile, bastion_id, args.forwardhost, args.port, args.sourceport)
    else:
        sys.exit("ERROR: You must specify either --shell or --db mode.")


if __name__ == "__main__":
    main()
