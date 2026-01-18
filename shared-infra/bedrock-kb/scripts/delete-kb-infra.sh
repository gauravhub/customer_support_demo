#!/bin/bash

# Script to delete Bedrock Knowledge Bases infrastructure
# Usage: ./delete-kb-infra.sh

set -e

# Default values
REGION="${REGION:-us-west-2}"
STACK_NAME="${STACK_NAME:-customer-support-demo-bedrock-kb}"

echo "=========================================="
echo "Delete Bedrock Knowledge Bases Infrastructure"
echo "=========================================="
echo "Region: $REGION"
echo "Stack Name: $STACK_NAME"
echo "=========================================="
echo ""

# Check if stack exists
if ! aws cloudformation describe-stacks --stack-name "$STACK_NAME" --region "$REGION" >/dev/null 2>&1; then
    echo "Stack $STACK_NAME does not exist."
    exit 0
fi

# Get S3 bucket name from stack outputs
S3_BUCKET_NAME=$(aws cloudformation describe-stacks \
    --stack-name "$STACK_NAME" \
    --region "$REGION" \
    --query 'Stacks[0].Outputs[?OutputKey==`S3BucketName`].OutputValue' \
    --output text 2>/dev/null || echo "")

echo "⚠️  WARNING: This will delete:"
echo "   - OpenSearch domain (this cannot be undone)"
echo "   - S3 bucket: $S3_BUCKET_NAME"
echo "   - IAM roles and policies"
echo "   - Secrets Manager secrets"
echo ""
read -p "Are you sure you want to continue? (type 'yes' to confirm): " -r
echo

if [ "$REPLY" != "yes" ]; then
    echo "Aborted."
    exit 0
fi

# Delete CloudFormation stack
echo "Deleting CloudFormation stack..."
aws cloudformation delete-stack \
    --stack-name "$STACK_NAME" \
    --region "$REGION"

echo ""
echo "Waiting for stack deletion to complete..."
echo "Note: OpenSearch domain deletion can take 10-15 minutes..."
aws cloudformation wait stack-delete-complete \
    --stack-name "$STACK_NAME" \
    --region "$REGION"

echo ""
echo "Stack deleted successfully!"
