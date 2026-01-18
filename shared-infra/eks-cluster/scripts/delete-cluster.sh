#!/bin/bash

# Script to delete EKS AutoMode cluster for customer-support-demo

set -e

# Configuration - can be overridden via environment variables
REGION="${REGION:-us-west-2}"
CLUSTER_NAME="${CLUSTER_NAME:-customer-support-demo}"

echo "=========================================="
echo "DELETING EKS CLUSTER"
echo "=========================================="
echo "Cluster Name: $CLUSTER_NAME"
echo "Region: $REGION"
echo ""

# Check if eksctl is available
if ! command -v eksctl &> /dev/null; then
    echo "Error: eksctl not found. Please install eksctl first."
    exit 1
fi

# Check if cluster exists
if ! eksctl get cluster --name "$CLUSTER_NAME" --region "$REGION" &>/dev/null; then
    echo "Cluster '$CLUSTER_NAME' does not exist in region $REGION."
    exit 0
fi

# Confirm deletion
read -p "Are you sure you want to delete cluster '$CLUSTER_NAME'? This cannot be undone! (yes/no) " -r
echo
if [[ ! $REPLY =~ ^[Yy][Ee][Ss]$ ]]; then
    echo "Deletion cancelled."
    exit 0
fi

echo "Deleting cluster..."
eksctl delete cluster --name "$CLUSTER_NAME" --region "$REGION"

echo ""
echo "Cluster deletion initiated. This may take 10-15 minutes."
echo ""
