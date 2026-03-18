#!/usr/bin/env bash
set -euo pipefail

###############################################################################
# Destroys Terraform-managed infrastructure and deletes:
# - All ELBs (classic and v2: ALB/NLB)
# - All security groups tagged kubernetes.io/cluster/1-node-default-vpc=owned
# - CloudWatch Logs log group /aws/eks/1-node-default-vpc/cluster
# in the current AWS account/region using the AWS CLI.
#
# Usage:
#   ./destroy-terraform-and-elb.sh [TERRAFORM_DIR]
#
# - TERRAFORM_DIR (optional): Directory containing Terraform configuration.
#   Defaults to current directory if not provided.
#
# Requirements:
# - terraform installed and on PATH
# - aws CLI v2 configured (AWS credentials + region via env or config)
###############################################################################

TERRAFORM_DIR="${1:-.}"

echo "=================================================================="
echo "Terraform destroy in directory: ${TERRAFORM_DIR}"
echo "=================================================================="

if [ ! -d "${TERRAFORM_DIR}" ]; then
  echo "ERROR: Terraform directory '${TERRAFORM_DIR}' does not exist." >&2
  exit 1
fi

if ! command -v terraform >/dev/null 2>&1; then
  echo "ERROR: terraform command not found on PATH." >&2
  exit 1
fi

if ! command -v aws >/dev/null 2>&1; then
  echo "ERROR: aws CLI command not found on PATH." >&2
  exit 1
fi

pushd "${TERRAFORM_DIR}" >/dev/null

if [ -f "terraform.tfstate" ] || [ -d ".terraform" ]; then
  echo "Running 'terraform destroy -auto-approve'..."
  terraform destroy -auto-approve
else
  echo "No Terraform state or .terraform directory found in '${TERRAFORM_DIR}'. Skipping terraform destroy."
fi

popd >/dev/null

echo
echo "=================================================================="
echo "Deleting ALL Elastic Load Balancers, tagged Security Groups, and EKS log group in this AWS account/region"
echo "=================================================================="
echo "This will remove:"
echo "  - Classic ELBs (aws elb)"
echo "  - ALBs/NLBs (aws elbv2)"
echo "  - Security groups tagged kubernetes.io/cluster/1-node-default-vpc=owned"
echo "  - CloudWatch log group /aws/eks/1-node-default-vpc/cluster"
echo
#read -p "Type 'delete' to proceed, or anything else to abort: " CONFIRM
#if [ "${CONFIRM}" != "delete" ]; then
#  echo "Aborted by user."
#  exit 0
#fi

AWS_REGION="${AWS_REGION:-${AWS_DEFAULT_REGION:-}}"
if [ -z "${AWS_REGION}" ]; then
  echo "INFO: No AWS_REGION/AWS_DEFAULT_REGION set; relying on AWS CLI default region/config."
else
  echo "Using AWS region: ${AWS_REGION}"
fi

###############################################################################
# Delete classic ELBs (aws elb)
###############################################################################
echo
echo "Fetching classic ELBs (aws elb)..."
CLASSIC_ELBS=$(aws elb describe-load-balancers \
  ${AWS_REGION:+--region "${AWS_REGION}"} \
  --query 'LoadBalancerDescriptions[].LoadBalancerName' \
  --output text || true)

if [ -z "${CLASSIC_ELBS}" ] || [ "${CLASSIC_ELBS}" = "None" ]; then
  echo "No classic ELBs found."
else
  echo "Classic ELBs to delete:"
  for name in ${CLASSIC_ELBS}; do
    echo "  - ${name}"
  done

  for name in ${CLASSIC_ELBS}; do
    echo "Deleting classic ELB: ${name}"
    aws elb delete-load-balancer \
      ${AWS_REGION:+--region "${AWS_REGION}"} \
      --load-balancer-name "${name}" || echo "WARNING: Failed to delete classic ELB ${name}"
  done
fi

###############################################################################
# Delete ALB/NLB (ELBv2) load balancers (aws elbv2)
###############################################################################
echo
echo "Fetching ELBv2 load balancers (ALB/NLB) (aws elbv2)..."
ELBV2_ARNS=$(aws elbv2 describe-load-balancers \
  ${AWS_REGION:+--region "${AWS_REGION}"} \
  --query 'LoadBalancers[].LoadBalancerArn' \
  --output text || true)

if [ -z "${ELBV2_ARNS}" ] || [ "${ELBV2_ARNS}" = "None" ]; then
  echo "No ELBv2 load balancers found."
else
  echo "ELBv2 load balancers to delete:"
  for arn in ${ELBV2_ARNS}; do
    echo "  - ${arn}"
  done

  for arn in ${ELBV2_ARNS}; do
    echo "Deleting ELBv2 load balancer: ${arn}"
    aws elbv2 delete-load-balancer \
      ${AWS_REGION:+--region "${AWS_REGION}"} \
      --load-balancer-arn "${arn}" || echo "WARNING: Failed to delete ELBv2 load balancer ${arn}"
  done
fi

###############################################################################
# Delete Security Groups with tag kubernetes.io/cluster/1-node-default-vpc=owned
###############################################################################
echo
echo "Fetching security groups tagged kubernetes.io/cluster/1-node-default-vpc=owned..."
SG_IDS=$(aws ec2 describe-security-groups \
  ${AWS_REGION:+--region "${AWS_REGION}"} \
  --filters "Name=tag:kubernetes.io/cluster/1-node-default-vpc,Values=owned" \
  --query 'SecurityGroups[].GroupId' \
  --output text || true)

if [ -z "${SG_IDS}" ] || [ "${SG_IDS}" = "None" ]; then
  echo "No matching security groups found."
else
  echo "Security groups to delete:"
  for sg in ${SG_IDS}; do
    echo "  - ${sg}"
  done

  for sg in ${SG_IDS}; do
    echo "Deleting security group: ${sg}"
    aws ec2 delete-security-group \
      ${AWS_REGION:+--region "${AWS_REGION}"} \
      --group-id "${sg}" || echo "WARNING: Failed to delete security group ${sg} (may still be attached or referenced)"
  done
fi

###############################################################################
# Delete unattached EBS volumes tagged for the cluster
###############################################################################
echo
echo "Fetching unattached EBS volumes tagged kubernetes.io/cluster/1-node-default-vpc=owned..."
VOLUME_IDS=$(aws ec2 describe-volumes \
  ${AWS_REGION:+--region "${AWS_REGION}"} \
  --filters \
    "Name=status,Values=available" \
    "Name=tag:kubernetes.io/cluster/1-node-default-vpc,Values=owned" \
  --query 'Volumes[].VolumeId' \
  --output text || true)

if [ -z "${VOLUME_IDS}" ] || [ "${VOLUME_IDS}" = "None" ]; then
  echo "No matching unattached EBS volumes found."
else
  echo "EBS volumes to delete:"
  for vol in ${VOLUME_IDS}; do
    echo "  - ${vol}"
  done

  for vol in ${VOLUME_IDS}; do
    echo "Deleting EBS volume: ${vol}"
    aws ec2 delete-volume \
      ${AWS_REGION:+--region "${AWS_REGION}"} \
      --volume-id "${vol}" || echo "WARNING: Failed to delete EBS volume ${vol}"
  done
fi

###############################################################################
# Delete CloudWatch Logs log group for EKS cluster
###############################################################################
LOG_GROUP_NAME="/aws/eks/1-node-default-vpc/cluster"
echo "Checking for CloudWatch Logs log group: ${LOG_GROUP_NAME}"

LOG_GROUP_EXISTS=$(aws logs describe-log-groups \
  ${AWS_REGION:+--region "${AWS_REGION}"} \
  --log-group-name-prefix "${LOG_GROUP_NAME}" \
  --query "logGroups[?logGroupName=='${LOG_GROUP_NAME}'].logGroupName" \
  --output text || true)

if [ -z "${LOG_GROUP_EXISTS}" ] || [ "${LOG_GROUP_EXISTS}" = "None" ]; then
  echo "Log group ${LOG_GROUP_NAME} not found."
else
  echo "Deleting log group: ${LOG_GROUP_NAME}"
  aws logs delete-log-group \
    ${AWS_REGION:+--region "${AWS_REGION}"} \
    --log-group-name "${LOG_GROUP_NAME}" || echo "WARNING: Failed to delete log group ${LOG_GROUP_NAME}"
fi

echo
echo "Done. Terraform (if present) destroyed, all ELBs removed, tagged security groups deleted (where possible), and EKS log group cleaned up."

