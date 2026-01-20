#!/bin/bash

# Script to build, push, and deploy issue-management-api
# Usage: ./scripts/build-and-deploy.sh [ACCOUNT_ID] [REGION]
#   If ACCOUNT_ID and REGION are not provided, they will be read from environment variables

set -e

# Get ACCOUNT_ID and REGION from arguments or environment variables
ACCOUNT_ID="${1:-${ACCOUNT_ID}}"
REGION="${2:-${REGION:-us-west-2}}"

# Try to get ACCOUNT_ID from AWS CLI if not provided
if [ -z "$ACCOUNT_ID" ]; then
    if command -v aws &> /dev/null; then
        ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text 2>/dev/null || echo "")
    fi
fi

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
echo "BUILDING AND DEPLOYING ISSUE MANAGEMENT API"
echo "=========================================="
echo "Account ID: $ACCOUNT_ID"
echo "Region: $REGION"
echo ""

# Get the directory where the script is located
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

# ECR repository name
ECR_REPO="issue-management-api"
ECR_URI="${ACCOUNT_ID}.dkr.ecr.${REGION}.amazonaws.com/${ECR_REPO}:latest"

echo "Step 1: Building Docker image..."
cd "$PROJECT_DIR"
docker build -t "$ECR_REPO:latest" -t "$ECR_URI" .

echo ""
echo "Step 2: Logging into ECR..."
aws ecr get-login-password --region "$REGION" | docker login --username AWS --password-stdin "${ACCOUNT_ID}.dkr.ecr.${REGION}.amazonaws.com"

echo ""
echo "Step 3: Creating ECR repository if it doesn't exist..."
aws ecr describe-repositories --repository-names "$ECR_REPO" --region "$REGION" 2>/dev/null || \
    aws ecr create-repository --repository-name "$ECR_REPO" --region "$REGION" > /dev/null

echo ""
echo "Step 4: Pushing Docker image to ECR..."
docker push "$ECR_URI"

echo ""
echo "Step 5: Deploying to Kubernetes..."
"$SCRIPT_DIR/deploy.sh" "$ACCOUNT_ID" "$REGION"

echo ""
echo "=========================================="
echo "BUILD AND DEPLOYMENT COMPLETE"
echo "=========================================="
echo ""
echo "Image: $ECR_URI"
echo ""
echo "To check deployment status:"
echo "  kubectl get deployment issue-management-api"
echo "  kubectl get pods -l app=issue-management-api"
echo ""
echo "To view logs:"
echo "  kubectl logs -f deployment/issue-management-api"
echo ""
