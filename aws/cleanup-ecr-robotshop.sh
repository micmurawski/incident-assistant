#!/usr/bin/env bash
set -euo pipefail

###############################################################################
# Cleanup Robot Shop images from ECR.
#
# By default this:
#   - Finds all ECR repositories under the "robotshop" namespace
#   - Deletes all images from those repositories
#   - Keeps the repositories (safer)
#
# Set DELETE_REPOSITORIES=true to also delete the repositories themselves.
#
# Environment variables:
#   AWS_REGION           - AWS region (default: us-east-1)
#   AWS_ACCOUNT_ID       - AWS account ID (default: 189429133920)
#   IMAGE_NAMESPACE      - ECR namespace/prefix (default: robotshop)
#   DELETE_REPOSITORIES  - "true" to delete repos after pruning images (default: false)
###############################################################################

AWS_REGION="${AWS_REGION:-us-east-1}"
AWS_ACCOUNT_ID="${AWS_ACCOUNT_ID:-189429133920}"
IMAGE_PREFIX="${IMAGE_PREFIX:-robot-shop-}"
DELETE_REPOSITORIES="${DELETE_REPOSITORIES:-false}"

ECR_REGISTRY="${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com"

echo "-------------------------------------------"
echo "ECR cleanup for Robot Shop"
echo "Region:             ${AWS_REGION}"
echo "Account:            ${AWS_ACCOUNT_ID}"
echo "Image prefix:       ${IMAGE_PREFIX}"
echo "Delete repositories: ${DELETE_REPOSITORIES}"
echo "Registry:           ${ECR_REGISTRY}"
echo "-------------------------------------------"

echo "Logging in to ECR..."
aws ecr get-login-password --region "${AWS_REGION}" \
  | docker login --username AWS --password-stdin "${ECR_REGISTRY}"

echo "Listing repositories with prefix '${IMAGE_PREFIX}'..."
repos=$(aws ecr describe-repositories \
  --region "${AWS_REGION}" \
  --query "repositories[?starts_with(repositoryName, \`${IMAGE_PREFIX}\`)].repositoryName" \
  --output text)

if [[ -z "${repos}" ]]; then
  echo "No repositories found with prefix '${IMAGE_PREFIX}'. Nothing to do."
  exit 0
fi

for repo in ${repos}; do
  echo "-------------------------------------------"
  echo "Processing repository: ${repo}"

  image_ids=$(aws ecr list-images \
    --region "${AWS_REGION}" \
    --repository-name "${repo}" \
    --query 'imageIds[*]' \
    --output json)

  if [[ "${image_ids}" == "[]" ]]; then
    echo "  No images found, skipping delete-images."
  else
    echo "  Deleting all images..."
    aws ecr batch-delete-image \
      --region "${AWS_REGION}" \
      --repository-name "${repo}" \
      --image-ids "${image_ids}" >/dev/null
    echo "  Images deleted."
  fi

  if [[ "${DELETE_REPOSITORIES}" == "true" ]]; then
    echo "  Deleting repository '${repo}'..."
    aws ecr delete-repository \
      --region "${AWS_REGION}" \
      --repository-name "${repo}" \
      --force >/dev/null
    echo "  Repository deleted."
  fi
done

echo "-------------------------------------------"
echo "✅ ECR cleanup complete."
echo "-------------------------------------------"

