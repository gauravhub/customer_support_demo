#!/bin/bash

# Script to create EKS AutoMode cluster for customer-support-demo
# This cluster will host both order-management-api and issue-management-api

set -e

# Configuration - can be overridden via environment variables
REGION="${REGION:-us-west-2}"
CLUSTER_NAME="${CLUSTER_NAME:-customer-support-demo}"
CLUSTER_VERSION="${CLUSTER_VERSION:-1.34}"

echo "=========================================="
echo "CREATING EKS CLUSTER"
echo "=========================================="
echo "Cluster Name: $CLUSTER_NAME"
echo "Region: $REGION"
echo "Kubernetes Version: $CLUSTER_VERSION"
echo ""

# Check if eksctl is available
if ! command -v eksctl &> /dev/null; then
    echo "Error: eksctl not found. Please install eksctl first."
    echo "Installation: https://eksctl.io/introduction/installation/"
    exit 1
fi

# Check eksctl version
EKSCTL_VERSION=$(eksctl version | grep -oE '[0-9]+\.[0-9]+\.[0-9]+' | head -n1 | cut -d'.' -f1,2)
REQUIRED_VERSION="0.221"
if [ -z "$EKSCTL_VERSION" ] || [ "$(printf '%s\n' "$REQUIRED_VERSION" "$EKSCTL_VERSION" | sort -V | head -n1)" != "$REQUIRED_VERSION" ]; then
    FULL_VERSION=$(eksctl version 2>/dev/null || echo "unknown")
    echo "Error: eksctl version 0.221.0 or greater is required."
    echo "Current version: $FULL_VERSION"
    echo "Please upgrade: https://eksctl.io/introduction/installation/"
    exit 1
fi

# Check if AWS CLI is available
if ! command -v aws &> /dev/null; then
    echo "Error: AWS CLI not found. Please install AWS CLI first."
    exit 1
fi

# Check if cluster already exists
if eksctl get cluster --name "$CLUSTER_NAME" --region "$REGION" &>/dev/null; then
    echo "Cluster '$CLUSTER_NAME' already exists in region $REGION."
    read -p "Do you want to delete and recreate it? (y/n) " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        echo "Deleting existing cluster..."
        eksctl delete cluster --name "$CLUSTER_NAME" --region "$REGION"
        echo "Waiting for cluster deletion to complete..."
        sleep 30
    else
        echo "Using existing cluster."
        echo ""
        echo "To configure kubectl:"
        echo "  aws eks update-kubeconfig --name $CLUSTER_NAME --region $REGION"
        exit 0
    fi
fi

# Update region in cluster.yaml if different from default
if [ "$REGION" != "us-west-2" ]; then
    echo "Updating region in cluster.yaml..."
    sed -i.bak "s/region: us-west-2/region: $REGION/" manifests/cluster.yaml
    sed -i.bak "s/version: \"1.34\"/version: \"$CLUSTER_VERSION\"/" manifests/cluster.yaml
fi

# Create the cluster
echo "Creating EKS AutoMode cluster..."
echo "This will take 15-20 minutes. Please wait..."
echo ""

eksctl create cluster -f manifests/cluster.yaml

# Configure kubectl
echo ""
echo "Configuring kubectl..."
aws eks update-kubeconfig --name "$CLUSTER_NAME" --region "$REGION"

# Apply IngressClass and IngressClassParams
echo ""
echo "Setting up IngressClass and IngressClassParams..."
kubectl apply -f manifests/ingressclassparams.yaml
kubectl apply -f manifests/ingressclass.yaml

# Verify cluster
echo ""
echo "Verifying cluster..."
kubectl get nodes
kubectl get ingressclass

echo ""
echo "=========================================="
echo "CLUSTER CREATION COMPLETE"
echo "=========================================="
echo "Cluster Name: $CLUSTER_NAME"
echo "Region: $REGION"
echo ""
echo "Next steps:"
echo "1. Deploy your APIs to this cluster"
echo "2. Create CloudFront distribution: cd ../cloudfront && ./scripts/create-distribution.sh"
echo ""
echo "To delete the cluster:"
echo "  eksctl delete cluster --name $CLUSTER_NAME --region $REGION"
echo ""
