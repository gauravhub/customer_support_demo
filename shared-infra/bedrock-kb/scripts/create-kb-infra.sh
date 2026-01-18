#!/bin/bash

# Script to create Bedrock Knowledge Bases infrastructure
# Usage: ./create-kb-infra.sh

set -e

# Default values
REGION="${REGION:-us-west-2}"
STACK_NAME="${STACK_NAME:-customer-support-demo-bedrock-kb}"
OPENSEARCH_DOMAIN_NAME="${OPENSEARCH_DOMAIN_NAME:-cs-demo-kb-opensearch}"
ADMIN_USER_NAME="${ADMIN_USER_NAME:-admin}"

# Get AWS account ID
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
if [ -z "$ACCOUNT_ID" ]; then
    echo "Error: Could not get AWS account ID. Is AWS CLI configured?"
    exit 1
fi

# Generate S3 bucket name (must be globally unique)
S3_BUCKET_NAME="${S3_BUCKET_NAME:-customer-support-kb-datasources-${ACCOUNT_ID}}"

# Generate a random password for OpenSearch admin user
ADMIN_USER_PASSWORD="${ADMIN_USER_PASSWORD:-$(openssl rand -base64 16)}"

echo "=========================================="
echo "Bedrock Knowledge Bases Infrastructure"
echo "=========================================="
echo "Region: $REGION"
echo "Stack Name: $STACK_NAME"
echo "OpenSearch Domain: $OPENSEARCH_DOMAIN_NAME"
echo "S3 Bucket: $S3_BUCKET_NAME"
echo "Admin User: $ADMIN_USER_NAME"
echo "=========================================="
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
    --template-body file://$(dirname "$0")/../manifests/bedrock-kb.yaml \
    --parameters \
        ParameterKey=OpenSearchDomainName,ParameterValue="$OPENSEARCH_DOMAIN_NAME" \
        ParameterKey=S3BucketName,ParameterValue="$S3_BUCKET_NAME" \
        ParameterKey=AdminUserName,ParameterValue="$ADMIN_USER_NAME" \
        ParameterKey=AdminUserPassword,ParameterValue="$ADMIN_USER_PASSWORD" \
    --capabilities CAPABILITY_NAMED_IAM \
    --region "$REGION" \
    --tags \
        Key=Environment,Value=demo \
        Key=Purpose,Value=BedrockKnowledgeBase

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
echo "Important Information:"
echo "=========================================="
echo "OpenSearch Admin User Password: $ADMIN_USER_PASSWORD"
echo "(This password is also stored in Secrets Manager)"
echo ""
echo "Next Steps:"
echo "1. Note the OpenSearchDomainEndpoint and S3BucketName from outputs above"
echo "2. Use these values in product-knowledge-base/.env file"
echo "3. Run product-knowledge-base ingestion scripts to upload data"
echo ""
