# BASTION

## NAME

**bastion.py** - AWS Systems Manager Session Manager connection utility

## SYNOPSIS

```
bastion.py --shell --profile PROFILE [--host HOST] [--org ORG]
bastion.py --forward --profile PROFILE [--forwardhost FQDN] [--host HOST] [--port PORT] [--sourceport PORT] [--org ORG]
```

## DESCRIPTION

**bastion.py** is a Python-based CLI tool that simplifies connecting to AWS EC2 bastion hosts using AWS Systems Manager (SSM) Session Manager. It supports two modes of operation: interactive shell access and port forwarding for database or service connections.

The script handles AWS SSO authentication automatically, resolves EC2 instance names to instance IDs, and initiates SSM sessions using the AWS CLI. Instance hosts can be specified by their Name tag or directly by instance ID.

A key security benefit of using SSM with a bastion EC2 instance is that connections are established through AWS SSM Service Endpoints. This means you can connect securely without opening SSH ports (22) or any other inbound ports to the internet, significantly reducing the attack surface of your infrastructure.

## OPTIONS

### Required Options

**-s, --shell**  
    Enable interactive shell mode. Opens a shell session on the specified bastion host.

**-f, --forward**  
    Enable port forwarding mode. Creates a tunnel from a local port through the bastion host to a remote service.

**-p PROFILE, --profile PROFILE**  
    AWS profile name to use for authentication (required).

Note: Either `--shell` or `--forward` must be specified, but not both.

### Optional Options

**-o ORG, --org ORG**  
    AWS SSO session/organization name (default: awsorg). This is used when authenticating with AWS SSO.

**-H HOST, --host HOST**  
    Remote EC2 host to connect to. Can be specified as:
    - EC2 instance Name tag (default: "bastion-host-ephemeral")
    - EC2 instance ID (format: i-[a-z0-9]{17})
    
**-F FQDN, --forwardhost FQDN**  
    Target hostname or IP address to forward traffic to (used with --forward mode). Typically an RDS endpoint or internal service address.

**-P PORT, --port PORT**  
    Local port number for port forwarding (default: 3306). Valid range: 0-65535.

**-S PORT, --sourceport PORT**  
    Remote port number on the target host (default: 3306). Valid range: 0-65535.

## EXAMPLES

### Interactive Shell Access

Connect to the default bastion host using the devprofile profile:
```bash
bastion.py --shell --profile devprofile
```

Connect to a specific host by name:
```bash
bastion.py -s -H myhost -p prodprofile
```

Connect using an instance ID directly:
```bash
bastion.py -s -H i-0123456abcdefg -p devprofile
```

### Port Forwarding

Forward local port 3306 to an RDS database through the bastion:
```bash
bastion.py --forward --forwardhost db-dev-001.xxxxxxxxxxxxxxx.us-east-2.rds.amazonaws.com --profile devprofile
```

Forward local port 5432 to a PostgreSQL database on port 5432:
```bash
bastion.py -f -F postgres-prod.internal.com -P 5432 -S 5432 -p prodprofile
```

Forward to a custom service using non-standard ports:
```bash
bastion.py -f -F my-server.internal.com -P 8080 -S 8443 -p devprofile
```

### Shell Aliases

Add these to your `.bashrc` or `.zshrc` for convenience:
```bash
# Custom Aliases & Functions
alias bastion='~/bin/bastion.py'
alias s-dev='~/bin/bastion.py -s -p devprofile'
alias f-dev='~/bin/bastion.py -f -F db-dev-001.xxxxxxxxxxxxxxx.us-east-2.rds.amazonaws.com -p devprofile'

# Function for quick shell access
awshell() {
    ~/bin/bastion.py -s -p "$1"
}
```

Usage:
```bash
awshell devprofile
s-dev
f-dev
```

## AUTHENTICATION

The script uses AWS SSO for authentication and will automatically prompt for login if your session has expired. The SSO session name defaults to "awsorg" but can be customized using the `--org` parameter.

Before the SSM session begins, the script validates authentication by calling `sts:GetCallerIdentity` and displays the assumed role ARN.

## INSTANCE DISCOVERY

When a host is specified by Name tag, the script:
1. Queries EC2 for instances matching the Name tag
2. Filters for instances in "running" state only
3. Returns an error if zero or multiple instances are found
4. Validates the instance ID format before proceeding

When an instance ID is provided directly (format: `i-` followed by 17 alphanumeric characters), the script bypasses the EC2 query and uses the ID directly.

## EXIT STATUS

**0**  
    Successful completion

**Non-zero**  
    An error occurred. Common errors include:
    - AWS SSO authentication failure
    - No instances found with the specified name
    - Multiple instances found with the same name (use instance ID instead)
    - Invalid port number
    - Invalid instance ID format

## REQUIREMENTS

- Python 3
- AWS CLI configured with SSM Session Manager plugin
- boto3 Python library
- Valid AWS SSO configuration
- Linux EC2 instance with Name tag = "bastion-host-ephemeral" is required for port forwarding
- Appropriate IAM permissions for:
  - EC2 DescribeInstances
  - SSM StartSession

## SEE ALSO

aws-cli(1), aws-ssm(1), boto3 documentation

## NOTES

This script uses the AWS CLI for establishing SSM sessions rather than boto3 because the CLI maintains persistent tunnel connections, which is necessary for interactive sessions and port forwarding.
