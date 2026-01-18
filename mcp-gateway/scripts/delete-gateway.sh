#!/bin/bash

# Script to delete MCP Gateway CloudFormation stack
# Usage: ./delete-gateway.sh

set -e

# Default values
REGION="${REGION:-us-west-2}"
STACK_NAME="${STACK_NAME:-customer-support-demo-mcp-gateway}"

echo "=========================================="
echo "Delete MCP Gateway Stack"
echo "=========================================="
echo "Stack Name: $STACK_NAME"
echo "Region: $REGION"
echo ""

# Check if stack exists
if ! aws cloudformation describe-stacks --stack-name "$STACK_NAME" --region "$REGION" >/dev/null 2>&1; then
    echo "Stack $STACK_NAME does not exist."
    exit 0
fi

# Confirm deletion
read -p "Are you sure you want to delete stack $STACK_NAME? (y/n): " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "Aborted."
    exit 0
fi

echo ""
echo "Deleting stack..."
aws cloudformation delete-stack \
    --stack-name "$STACK_NAME" \
    --region "$REGION"

echo "Waiting for stack deletion to complete..."
aws cloudformation wait stack-delete-complete \
    --stack-name "$STACK_NAME" \
    --region "$REGION"

if [ $? -eq 0 ]; then
    echo ""
    echo "✓ Stack deleted successfully"
    echo ""
    echo "Note: API key providers are NOT deleted by this script."
    echo "To delete API key providers, use AWS Console or CLI manually."
else
    echo ""
    echo "Error: Stack deletion failed or timed out"
    echo "Check CloudFormation console for details"
    exit 1
fi
