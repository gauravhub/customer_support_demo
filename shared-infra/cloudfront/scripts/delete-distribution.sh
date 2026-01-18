#!/bin/bash

# Script to delete CloudFront distribution for customer-support-demo

set -e

# Configuration - can be overridden via environment variables
REGION="${REGION:-us-west-2}"
STACK_NAME="${STACK_NAME:-customer-support-demo-cloudfront}"

echo "=========================================="
echo "DELETING CLOUDFRONT DISTRIBUTION"
echo "=========================================="
echo "Stack Name: $STACK_NAME"
echo "Region: $REGION"
echo ""

# Check if AWS CLI is available
if ! command -v aws &> /dev/null; then
    echo "Error: AWS CLI not found. Please install AWS CLI first."
    exit 1
fi

# Check if stack exists
if ! aws cloudformation describe-stacks --stack-name "$STACK_NAME" --region "$REGION" &>/dev/null; then
    echo "CloudFormation stack '$STACK_NAME' does not exist in region $REGION."
    exit 0
fi

# Confirm deletion
read -p "Are you sure you want to delete CloudFront distribution '$STACK_NAME'? This cannot be undone! (yes/no) " -r
echo
if [[ ! $REPLY =~ ^[Yy][Ee][Ss]$ ]]; then
    echo "Deletion cancelled."
    exit 0
fi

echo "Deleting CloudFormation stack..."
aws cloudformation delete-stack --stack-name "$STACK_NAME" --region "$REGION"

echo ""
echo "CloudFront distribution deletion initiated."
echo "This may take 10-15 minutes to complete."
echo ""
