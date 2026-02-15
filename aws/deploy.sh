#!/bin/bash
set -e  # Exit immediately if any command fails

# Configuration - Must match your main.tf
REGION="us-east-1"
CLUSTER_NAME="1-node-default-vpc"

echo "🚀 Starting Deployment..."
echo "-----------------------------------"
# 1. Initialize Terraform
echo "📦 Initializing Terraform..."
terraform init -reconfigure

# 2. Apply Terraform
# -auto-approve skips the "yes" prompt for automation
echo "🏗️  Applying Terraform configuration..."
echo "⏳ Please wait! EKS creation usually takes 10-15 minutes on AWS..."
terraform apply -auto-approve

echo "-----------------------------------"
echo "✅ Infrastructure created successfully!"

# 3. Configure kubectl
# This connects your local terminal to the new cluster on AWS
echo "🔗 Connecting kubectl to EKS..."
aws eks update-kubeconfig --region $REGION --name $CLUSTER_NAME

# 4. Verify the Node
echo "🔍 Verifying cluster status..."
# We wait a moment for the node to register
sleep 10
kubectl get nodes

echo "-----------------------------------"
echo "🎉 Cluster is ready! You can now use 'kubectl' commands."