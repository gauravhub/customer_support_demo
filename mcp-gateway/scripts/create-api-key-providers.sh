#!/bin/bash

# Script to create API key providers for AgentCore Gateway targets
# These must be created BEFORE deploying the CloudFormation stack
# Usage: ./create-api-key-providers.sh

set -e

# Default values
REGION="${REGION:-us-west-2}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

echo "=========================================="
echo "Create API Key Providers"
echo "=========================================="
echo "Region: $REGION"
echo ""

# API Keys (from the APIs)
# IMPORTANT: Set your own API keys via environment variables
# Do not use the example keys shown in documentation in production
ORDER_MANAGEMENT_API_KEY="${ORDER_MANAGEMENT_API_KEY:-}"
ISSUE_MANAGEMENT_API_KEY="${ISSUE_MANAGEMENT_API_KEY:-}"

if [ -z "$ORDER_MANAGEMENT_API_KEY" ] || [ -z "$ISSUE_MANAGEMENT_API_KEY" ]; then
    echo "Error: API keys must be set via environment variables"
    echo ""
    echo "Usage:"
    echo "  export ORDER_MANAGEMENT_API_KEY=your-base64-encoded-key"
    echo "  export ISSUE_MANAGEMENT_API_KEY=your-base64-encoded-key"
    echo "  ./create-api-key-providers.sh"
    echo ""
    echo "To generate a random API key (example):"
    echo "  openssl rand -base64 32"
    exit 1
fi

# Provider names
ORDER_PROVIDER_NAME="order-management-api-key-provider"
ISSUE_PROVIDER_NAME="issue-management-api-key-provider"

echo "Creating API key providers..."
echo ""

# Check if providers already exist
ORDER_PROVIDER_ARN=$(aws bedrock-agentcore-control list-api-key-credential-providers \
    --region "$REGION" \
    --query "credentialProviders[?name=='$ORDER_PROVIDER_NAME'].credentialProviderArn" \
    --output text 2>/dev/null | head -n1 || echo "")

ISSUE_PROVIDER_ARN=$(aws bedrock-agentcore-control list-api-key-credential-providers \
    --region "$REGION" \
    --query "credentialProviders[?name=='$ISSUE_PROVIDER_NAME'].credentialProviderArn" \
    --output text 2>/dev/null | head -n1 || echo "")

# Create Order Management API key provider
if [ -z "$ORDER_PROVIDER_ARN" ]; then
    echo "Creating Order Management API key provider..."
    ORDER_PROVIDER_ARN=$(aws bedrock-agentcore-control create-api-key-credential-provider \
        --name "$ORDER_PROVIDER_NAME" \
        --api-key "$ORDER_MANAGEMENT_API_KEY" \
        --region "$REGION" \
        --query 'credentialProviderArn' \
        --output text)
    
    if [ $? -eq 0 ] && [ -n "$ORDER_PROVIDER_ARN" ]; then
        echo "✓ Created: $ORDER_PROVIDER_NAME"
        echo "  ARN: $ORDER_PROVIDER_ARN"
    else
        echo "✗ Failed to create Order Management API key provider"
        exit 1
    fi
else
    echo "✓ Order Management API key provider already exists"
    echo "  ARN: $ORDER_PROVIDER_ARN"
fi

echo ""

# Create Issue Management API key provider
if [ -z "$ISSUE_PROVIDER_ARN" ]; then
    echo "Creating Issue Management API key provider..."
    ISSUE_PROVIDER_ARN=$(aws bedrock-agentcore-control create-api-key-credential-provider \
        --name "$ISSUE_PROVIDER_NAME" \
        --api-key "$ISSUE_MANAGEMENT_API_KEY" \
        --region "$REGION" \
        --query 'credentialProviderArn' \
        --output text)
    
    if [ $? -eq 0 ] && [ -n "$ISSUE_PROVIDER_ARN" ]; then
        echo "✓ Created: $ISSUE_PROVIDER_NAME"
        echo "  ARN: $ISSUE_PROVIDER_ARN"
    else
        echo "✗ Failed to create Issue Management API key provider"
        exit 1
    fi
else
    echo "✓ Issue Management API key provider already exists"
    echo "  ARN: $ISSUE_PROVIDER_ARN"
fi

echo ""
echo "=========================================="
echo "API Key Providers Created"
echo "=========================================="
echo ""
echo "Export these ARNs as environment variables for CloudFormation:"
echo ""
echo "export ORDER_MANAGEMENT_API_KEY_PROVIDER_ARN=\"$ORDER_PROVIDER_ARN\""
echo "export ISSUE_MANAGEMENT_API_KEY_PROVIDER_ARN=\"$ISSUE_PROVIDER_ARN\""
echo ""
echo "Or use them directly in the create-gateway.sh script."
echo ""
