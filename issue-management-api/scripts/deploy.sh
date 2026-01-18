#!/bin/bash

# Script to deploy issue-management-api to Kubernetes
# Usage: ./scripts/deploy.sh [ACCOUNT_ID] [REGION]
#   If ACCOUNT_ID and REGION are not provided, they will be read from environment variables

set -e

# Get ACCOUNT_ID and REGION from arguments or environment variables
ACCOUNT_ID="${1:-${ACCOUNT_ID}}"
REGION="${2:-${REGION}}"

# Validate required variables
if [ -z "$ACCOUNT_ID" ] || [ -z "$REGION" ]; then
    echo "Error: ACCOUNT_ID and REGION must be provided"
    echo ""
    echo "Usage:"
    echo "  $0 [ACCOUNT_ID] [REGION]"
    echo ""
    echo "Or set environment variables:"
    echo "  export ACCOUNT_ID=123456789012"
    echo "  export REGION=us-west-2"
    echo "  $0"
    echo ""
    exit 1
fi

echo "=========================================="
echo "DEPLOYING ISSUE MANAGEMENT API"
echo "=========================================="
echo "Account ID: $ACCOUNT_ID"
echo "Region: $REGION"
echo ""

# Get the directory where the script is located
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MANIFEST_DIR="$(cd "$SCRIPT_DIR/../manifest" && pwd)"

# Check if kubectl is available
if ! command -v kubectl &> /dev/null; then
    echo "Error: kubectl not found. Please install kubectl first."
    exit 1
fi

# Check if kubectl is configured
if ! kubectl cluster-info &> /dev/null; then
    echo "Error: kubectl is not configured or cluster is not accessible."
    echo "Please configure kubectl: aws eks update-kubeconfig --name <cluster-name> --region $REGION"
    exit 1
fi

# Create temporary directory for processed manifests
TEMP_DIR=$(mktemp -d)
trap "rm -rf $TEMP_DIR" EXIT

echo "Processing deployment manifest..."
# Replace placeholders in deployment.yaml
sed "s/ACCOUNT_ID/$ACCOUNT_ID/g; s/REGION/$REGION/g" \
    "$MANIFEST_DIR/deployment.yaml" > "$TEMP_DIR/deployment.yaml"

echo "Deploying to Kubernetes..."
kubectl apply -f "$TEMP_DIR/deployment.yaml"
kubectl apply -f "$MANIFEST_DIR/service.yaml"
kubectl apply -f "$MANIFEST_DIR/ingress.yaml"

echo ""
echo "=========================================="
echo "DEPLOYMENT COMPLETE"
echo "=========================================="
echo ""
echo "To check deployment status:"
echo "  kubectl get deployment issue-management-api"
echo "  kubectl get pods -l app=issue-management-api"
echo ""
echo "To view logs:"
echo "  kubectl logs -f deployment/issue-management-api"
echo ""
echo "To get endpoint:"
echo "  kubectl get ingress issue-management-api-ingress -o jsonpath='{.status.loadBalancer.ingress[0].hostname}'"
echo ""
