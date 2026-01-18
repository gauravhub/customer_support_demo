#!/bin/bash

# Script to create Product Knowledge Base using CloudFormation
# Usage: ./create-kb.sh

set -e

# Default values
REGION="${REGION:-us-west-2}"
STACK_NAME="${STACK_NAME:-product-knowledge-base}"
S3_PREFIX="${S3_PREFIX:-product-information/}"
KB_NAME="${KB_NAME:-product-knowledge-base}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

echo "=========================================="
echo "Product Knowledge Base Deployment"
echo "=========================================="
echo "Region: $REGION"
echo "Stack Name: $STACK_NAME"
echo "S3 Prefix: $S3_PREFIX"
echo "KB Name: $KB_NAME"
echo "=========================================="
echo ""

# Get values from shared infrastructure stack
echo "Getting values from shared infrastructure stack..."
SHARED_STACK_NAME="${SHARED_STACK_NAME:-customer-support-demo-bedrock-kb}"

OPENSEARCH_DOMAIN_ENDPOINT_RAW=$(aws cloudformation describe-stacks \
    --stack-name "$SHARED_STACK_NAME" \
    --region "$REGION" \
    --query 'Stacks[0].Outputs[?OutputKey==`OpenSearchDomainEndpoint`].OutputValue' \
    --output text 2>/dev/null || echo "")

# Remove https:// if present (CloudFormation will add it)
OPENSEARCH_DOMAIN_ENDPOINT=$(echo "$OPENSEARCH_DOMAIN_ENDPOINT_RAW" | sed 's|^https://||')

OPENSEARCH_DOMAIN_ARN=$(aws cloudformation describe-stacks \
    --stack-name "$SHARED_STACK_NAME" \
    --region "$REGION" \
    --query 'Stacks[0].Outputs[?OutputKey==`OpenSearchDomainArn`].OutputValue' \
    --output text 2>/dev/null || echo "")

OPENSEARCH_ADMIN_USER_SECRET_ARN=$(aws cloudformation describe-stacks \
    --stack-name "$SHARED_STACK_NAME" \
    --region "$REGION" \
    --query 'Stacks[0].Outputs[?OutputKey==`OpenSearchAdminUserSecretArn`].OutputValue' \
    --output text 2>/dev/null || echo "")

S3_BUCKET_NAME=$(aws cloudformation describe-stacks \
    --stack-name "$SHARED_STACK_NAME" \
    --region "$REGION" \
    --query 'Stacks[0].Outputs[?OutputKey==`S3BucketName`].OutputValue' \
    --output text 2>/dev/null || echo "")

BEDROCK_KB_ROLE_ARN=$(aws cloudformation describe-stacks \
    --stack-name "$SHARED_STACK_NAME" \
    --region "$REGION" \
    --query 'Stacks[0].Outputs[?OutputKey==`BedrockKBRoleArn`].OutputValue' \
    --output text 2>/dev/null || echo "")

# Validate required values
if [ -z "$OPENSEARCH_DOMAIN_ENDPOINT" ] || [ -z "$OPENSEARCH_DOMAIN_ARN" ] || \
   [ -z "$S3_BUCKET_NAME" ] || [ -z "$BEDROCK_KB_ROLE_ARN" ]; then
    echo "Error: Could not get required values from shared infrastructure stack: $SHARED_STACK_NAME"
    echo "Please ensure the shared infrastructure is deployed first."
    exit 1
fi

echo "OpenSearch Domain Endpoint: $OPENSEARCH_DOMAIN_ENDPOINT"
echo "S3 Bucket: $S3_BUCKET_NAME"
echo ""

# Check if stack already exists
if aws cloudformation describe-stacks --stack-name "$STACK_NAME" --region "$REGION" >/dev/null 2>&1; then
    echo "Stack $STACK_NAME already exists."
    read -p "Do you want to update it? (y/n): " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo "Aborted."
        exit 0
    fi
    OPERATION="update"
else
    OPERATION="create"
fi

# Deploy CloudFormation stack
echo "Deploying CloudFormation stack..."
aws cloudformation ${OPERATION}-stack \
    --stack-name "$STACK_NAME" \
    --template-body file://"$PROJECT_DIR/manifests/product-kb.yaml" \
    --parameters \
        ParameterKey=OpenSearchDomainEndpoint,ParameterValue="$OPENSEARCH_DOMAIN_ENDPOINT" \
        ParameterKey=OpenSearchDomainArn,ParameterValue="$OPENSEARCH_DOMAIN_ARN" \
        ParameterKey=OpenSearchAdminUserSecretArn,ParameterValue="$OPENSEARCH_ADMIN_USER_SECRET_ARN" \
        ParameterKey=S3BucketName,ParameterValue="$S3_BUCKET_NAME" \
        ParameterKey=S3Prefix,ParameterValue="$S3_PREFIX" \
        ParameterKey=BedrockKBRoleArn,ParameterValue="$BEDROCK_KB_ROLE_ARN" \
        ParameterKey=KBName,ParameterValue="$KB_NAME" \
    --region "$REGION" \
    --tags \
        Key=Environment,Value=demo \
        Key=Purpose,Value=ProductKnowledgeBase

echo ""
echo "Waiting for stack ${OPERATION} to complete..."
aws cloudformation wait stack-${OPERATION}-complete \
    --stack-name "$STACK_NAME" \
    --region "$REGION"

# Get stack outputs
echo ""
echo "=========================================="
echo "Stack deployed successfully!"
echo "=========================================="
echo ""
echo "Stack Outputs:"
aws cloudformation describe-stacks \
    --stack-name "$STACK_NAME" \
    --region "$REGION" \
    --query 'Stacks[0].Outputs' \
    --output table

echo ""
echo "=========================================="
echo "Next Steps:"
echo "=========================================="
echo "1. Upload product data to S3:"
echo "   ./scripts/upload-data.sh"
echo ""
echo "2. Start ingestion job (after data is uploaded):"
echo "   aws bedrock-agent start-ingestion-job \\"
echo "     --knowledge-base-id <from-outputs> \\"
echo "     --data-source-id <from-outputs> \\"
echo "     --region $REGION"
echo ""
