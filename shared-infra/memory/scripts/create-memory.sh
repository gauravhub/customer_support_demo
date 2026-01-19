#!/bin/bash
# Script to deploy AgentCore Memory resource using CloudFormation
# This script deploys the CloudFormation stack which creates the memory resource

set -e

REGION="${AWS_REGION:-us-west-2}"
STACK_NAME="${STACK_NAME:-customer-support-memory}"
MEMORY_NAME="${MEMORY_NAME:-customer_support_agent}"
EVENT_EXPIRY_DAYS="${EVENT_EXPIRY_DAYS:-90}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TEMPLATE_FILE="${SCRIPT_DIR}/../manifests/memory-resource.yaml"

echo "Deploying AgentCore Memory: $MEMORY_NAME"
echo "Stack Name: $STACK_NAME"
echo "Region: $REGION"
echo "Event Expiry: $EVENT_EXPIRY_DAYS days"
echo ""

# Check if stack exists
if aws cloudformation describe-stacks --stack-name "$STACK_NAME" --region "$REGION" >/dev/null 2>&1; then
    echo "Stack $STACK_NAME already exists. Updating..."
    aws cloudformation update-stack \
        --stack-name "$STACK_NAME" \
        --template-body "file://${TEMPLATE_FILE}" \
        --parameters \
            ParameterKey=MemoryName,ParameterValue="$MEMORY_NAME" \
            ParameterKey=EventExpiryDays,ParameterValue="$EVENT_EXPIRY_DAYS" \
        --region "$REGION" \
        --capabilities CAPABILITY_NAMED_IAM || {
        # If update fails with "No updates are to be performed", that's okay
        if [ $? -eq 254 ]; then
            echo "No updates needed for stack $STACK_NAME"
        else
            exit 1
        fi
    }
    
    echo "Waiting for stack update to complete..."
    aws cloudformation wait stack-update-complete \
        --stack-name "$STACK_NAME" \
        --region "$REGION"
else
    echo "Creating new stack $STACK_NAME..."
    aws cloudformation create-stack \
        --stack-name "$STACK_NAME" \
        --template-body "file://${TEMPLATE_FILE}" \
        --parameters \
            ParameterKey=MemoryName,ParameterValue="$MEMORY_NAME" \
            ParameterKey=EventExpiryDays,ParameterValue="$EVENT_EXPIRY_DAYS" \
        --region "$REGION" \
        --capabilities CAPABILITY_NAMED_IAM
    
    echo "Waiting for stack creation to complete..."
    aws cloudformation wait stack-create-complete \
        --stack-name "$STACK_NAME" \
        --region "$REGION"
fi

echo ""
echo "Stack deployment completed successfully!"
echo ""
echo "Memory ID:"
aws cloudformation describe-stacks \
    --stack-name "$STACK_NAME" \
    --region "$REGION" \
    --query 'Stacks[0].Outputs[?OutputKey==`MemoryId`].OutputValue' \
    --output text

echo ""
echo "Memory ARN:"
aws cloudformation describe-stacks \
    --stack-name "$STACK_NAME" \
    --region "$REGION" \
    --query 'Stacks[0].Outputs[?OutputKey==`MemoryArn`].OutputValue' \
    --output text

echo ""
echo "Memory Status:"
aws cloudformation describe-stacks \
    --stack-name "$STACK_NAME" \
    --region "$REGION" \
    --query 'Stacks[0].Outputs[?OutputKey==`MemoryStatus`].OutputValue' \
    --output text
