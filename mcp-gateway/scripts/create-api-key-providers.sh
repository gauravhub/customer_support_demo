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
# Script reads from api_keys.json files in the API directories

# Paths to API key files
ORDER_MANAGEMENT_API_KEYS_FILE="$PROJECT_DIR/../order-management-api/data/api_keys.json"
ISSUE_MANAGEMENT_API_KEYS_FILE="$PROJECT_DIR/../issue-management-api/data/api_keys.json"

# Function to extract first API key from JSON array file
extract_api_key() {
    local file="$1"
    if [ -f "$file" ]; then
        # Extract first string from JSON array using grep and sed
        # Handles format: ["key"] or [ "key" ]
        grep -o '"[^"]*"' "$file" | head -n1 | sed 's/"//g'
    fi
}

# Read API keys from files
ORDER_MANAGEMENT_API_KEY=$(extract_api_key "$ORDER_MANAGEMENT_API_KEYS_FILE")
ISSUE_MANAGEMENT_API_KEY=$(extract_api_key "$ISSUE_MANAGEMENT_API_KEYS_FILE")

# Validate that API keys are available
if [ -z "$ORDER_MANAGEMENT_API_KEY" ] || [ -z "$ISSUE_MANAGEMENT_API_KEY" ]; then
    echo "Error: API keys not found in JSON files"
    echo ""
    echo "Required JSON files:"
    echo "  $ORDER_MANAGEMENT_API_KEYS_FILE"
    echo "  $ISSUE_MANAGEMENT_API_KEYS_FILE"
    echo ""
    if [ ! -f "$ORDER_MANAGEMENT_API_KEYS_FILE" ]; then
        echo "  ✗ Order Management API keys file not found"
    elif [ -z "$ORDER_MANAGEMENT_API_KEY" ]; then
        echo "  ✗ Order Management API keys file is empty or invalid"
    fi
    if [ ! -f "$ISSUE_MANAGEMENT_API_KEYS_FILE" ]; then
        echo "  ✗ Issue Management API keys file not found"
    elif [ -z "$ISSUE_MANAGEMENT_API_KEY" ]; then
        echo "  ✗ Issue Management API keys file is empty or invalid"
    fi
    echo ""
    echo "Expected JSON format: [\"your-base64-encoded-key\"]"
    exit 1
fi

# Show source of API keys
echo "API Keys loaded from JSON files:"
echo "  Order Management: $ORDER_MANAGEMENT_API_KEYS_FILE"
echo "  Issue Management: $ISSUE_MANAGEMENT_API_KEYS_FILE"
echo ""

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
