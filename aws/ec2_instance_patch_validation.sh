#!/usr/bin/env bash

# ==============================
# Purpose:
#   For each ADMIN SSO profile and region:
#   - Find running EC2 instances
#   - Use SSM to determine OS version
#   - Aggregate results safely
# ==============================

# Store final results
declare -a results=()

# Array with regions to check
REGIONS=("us-east-2" "us-west-2")

# --------------------------------------
# Build list of ADMIN SSO profiles only
# --------------------------------------
ADMIN_PROFILES=$(
  awk '
    # Capture profile name when we see a profile header
    /^\[profile / {
      profile=$0
      gsub(/^\[profile |\]$/, "", profile)
    }

    # If this profile has AdministratorAccess, include it
    /^sso_role_name *= *AdministratorAccess$/ {
      print profile
    }
  ' ~/.aws/config | sort -u
)

# Safety check
if [ -z "${ADMIN_PROFILES}" ]
then
  echo "No AdministratorAccess SSO profiles found. Exiting."
  exit 1
fi

# --------------------------------------
# Main processing loop
# --------------------------------------
for profile in ${ADMIN_PROFILES}
do
  for region in "${REGIONS[@]}"
  do

    AwsId=$(aws sts get-caller-identity \
      --profile ${profile} \
      --region ${region} \
      --query 'Account' \
      --output text 2>/dev/null)

    echo "Checking EC2 instances for profile: ${profile} | region: ${region} | AWS Account ID: ${AwsId}"

    InstanceIds=$(aws ec2 describe-instances \
      --profile ${profile} \
      --region ${region} \
      --query 'Reservations[].Instances[?State.Name==`running`].InstanceId' \
      --output text)

    # No instances is NOT an error — skip cleanly
    if [ -z "$InstanceIds" ]; then
      echo "No running EC2 instances found for profile: ${profile} | region: ${region}"
      continue
    fi

    # --------------------------------------
    # Per-instance processing
    # --------------------------------------
    for instance_id in ${InstanceIds}
    do
      echo "Checking instance: ${instance_id}"

      CommandId=$(aws ssm send-command \
        --profile ${profile} \
        --region ${region} \
        --instance-ids ${instance_id} \
        --document-name "AWS-RunShellScript" \
        --comment "Checking OS Patch Level" \
        --parameters 'commands=["grep PRETTY_NAME /etc/os-release"]' \
        --query 'Command.CommandId' \
        --output text)

      if [ -z "${CommandId}" ]
      then
        results+=("${profile}; ${region}; ${AwsId}; ${instance_id}; Failed to send SSM command")
        continue
      fi

      # Poll command status
      max_attempts=30
      attempt=0
      status=""

      while [ ${attempt} -lt ${max_attempts} ]
      do
        status=$(aws ssm get-command-invocation \
          --profile ${profile} \
          --region ${region} \
          --command-id ${CommandId} \
          --instance-id ${instance_id} \
          --query 'Status' \
          --output text 2>/dev/null)

        if [ "${status}" == "Success" ]
        then
          break
        elif [[ "${status}" == "Failed" || "${status}" == "Cancelled" || "${status}" == "TimedOut" ]]
        then
          break
        fi

        sleep 2
        attempt=$((attempt + 1))
      done

      if [ "${status}" == "Success" ]
      then
        output=$(aws ssm get-command-invocation \
          --profile ${profile} \
          --region ${region} \
          --command-id ${CommandId} \
          --instance-id ${instance_id} \
          --query 'StandardOutputContent' \
          --output text)

        output_clean=$(echo "${output}" | tr '\n' ' ' | sed 's/  */ /g' | xargs)

        results+=("${profile}; ${region}; ${AwsId}; ${instance_id}; ${output_clean}")
      else
        results+=("${profile}; ${region}; ${AwsId}; ${instance_id}; Command failed or timed out (Status: ${status})")
      fi
    done
  done
done

# --------------------------------------
# Print final results
# --------------------------------------
echo ""
echo "===== RESULTS ====="
for result in "${results[@]}"
do
  echo "${result}"
done
