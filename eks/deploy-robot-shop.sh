#!/usr/bin/env bash
set -euo pipefail

###############################################################################
# Build and deploy Robot Shop to EKS using ECR.
# - Builds all service images
# - Pushes them to ECR
# - Calls the k8s/deploy.sh script, which uses envsubst on robot-shop-eks.yaml
#
# Requirements:
# - AWS CLI configured (AWS_REGION / AWS_PROFILE etc.)
# - Docker logged in locally (this script will log in to ECR)
# - kubectl configured for your EKS cluster
###############################################################################

AWS_REGION="${AWS_REGION:-us-east-1}"
AWS_ACCOUNT_ID="${AWS_ACCOUNT_ID:-189429133920}"
TAG="${TAG:-2.2.0}"

# This is what robot-shop-eks.yaml and load-robot-shop.yaml use as ${REPO}
export REPO="${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com"
export TAG

folders=("cart" "catalogue" "dispatch" "load-gen" "mongo" "mysql" "payment" "ratings" "shipping" "user" "web")

get_repo_name() {
  local folder="$1"
  case "$folder" in
    mongo) echo "robot-shop-mongodb" ;;
    mysql) echo "robot-shop-mysql-db" ;;
    load-gen) echo "robot-shop-load-gen" ;;
    *) echo "robot-shop-${folder}" ;;
  esac
}

echo "-------------------------------------------"
echo "Building and pushing Robot Shop images"
echo "Region:        ${AWS_REGION}"
echo "Account:       ${AWS_ACCOUNT_ID}"
echo "ECR base repo: ${REPO}"
echo "Tag:           ${TAG}"
echo "-------------------------------------------"

echo "Logging in to ECR..."
aws ecr get-login-password --region "${AWS_REGION}" \
  | docker login --username AWS --password-stdin "${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com"

echo "Ensuring ECR repositories exist..."
for folder in "${folders[@]}"; do
  repo_name="$(get_repo_name "${folder}")"
  if ! aws ecr describe-repositories --region "${AWS_REGION}" --repository-names "${repo_name}" >/dev/null 2>&1; then
    echo "Creating ECR repo: ${repo_name}"
    aws ecr create-repository --region "${AWS_REGION}" --repository-name "${repo_name}" >/dev/null
  fi
done

echo "Building and pushing service images..."
pushd ../services/robot-shop >/dev/null
for folder in "${folders[@]}"; do
  repo_name="$(get_repo_name "${folder}")"
  full_image="${REPO}/${repo_name}:${TAG}"
  echo "-------------------------------------------"
  echo "Building ${folder} -> ${full_image}"
  docker build -t "${full_image}" "./${folder}"
  docker push "${full_image}"
done
popd >/dev/null

echo "-------------------------------------------"
echo "Deploying Robot Shop manifests to EKS..."
pushd ../services/robot-shop/k8s >/dev/null
./deploy.sh
popd >/dev/null

echo "-------------------------------------------"
echo "✅ Robot Shop deployment triggered."
echo "Use 'kubectl get pods -n robot-shop' and 'kubectl get svc -n robot-shop' to check status."
echo "-------------------------------------------"
