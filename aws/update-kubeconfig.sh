#!/usr/bin/env bash
# Update kubeconfig so kubectl uses this EKS cluster.
# Use the same IAM principal that created the cluster (e.g. AWS_PROFILE=robot).
# If you see "no such host" for *.eks.amazonaws.com, this script refreshes the endpoint.
set -e
CLUSTER_NAME="${CLUSTER_NAME:-1-node-default-vpc}"
REGION="${AWS_REGION:-us-east-1}"
echo "Cluster: $CLUSTER_NAME region: $REGION"
echo "Current AWS identity:"
aws sts get-caller-identity
echo ""
echo "Checking cluster exists..."
if ! aws eks describe-cluster --name "$CLUSTER_NAME" --region "$REGION" --query 'cluster.endpoint' --output text &>/dev/null; then
  echo "Cluster '$CLUSTER_NAME' not found in $REGION. Run 'terraform apply' in aws/ first."
  exit 1
fi
aws eks update-kubeconfig --name "$CLUSTER_NAME" --region "$REGION"
echo "Done. Test with: kubectl get nodes"
