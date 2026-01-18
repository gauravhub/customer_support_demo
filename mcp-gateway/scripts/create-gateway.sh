#!/bin/bash

# Script to deploy MCP Gateway with CloudFormation
# Usage: ./create-gateway.sh

set -e

# Default values
REGION="${REGION:-us-west-2}"
STACK_NAME="${STACK_NAME:-customer-support-demo-mcp-gateway}"
COGNITO_DOMAIN_PREFIX="${COGNITO_DOMAIN_PREFIX:-customer-support-mcp-gateway}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

echo "=========================================="
echo "MCP Gateway Deployment"
echo "=========================================="
echo "Region: $REGION"
echo "Stack Name: $STACK_NAME"
echo "=========================================="
echo ""

# Step 1: Create API key providers (if not already created)
echo "Step 1: Checking/Creating API key providers..."

# Check if providers already exist
ORDER_PROVIDER_ARN=$(aws bedrock-agentcore-control list-api-key-credential-providers \
    --region "$REGION" \
    --query "credentialProviders[?name=='order-management-api-key-provider'].credentialProviderArn" \
    --output text 2>/dev/null | head -n1 || echo "")

ISSUE_PROVIDER_ARN=$(aws bedrock-agentcore-control list-api-key-credential-providers \
    --region "$REGION" \
    --query "credentialProviders[?name=='issue-management-api-key-provider'].credentialProviderArn" \
    --output text 2>/dev/null | head -n1 || echo "")

# If not found, try to create them
if [ -z "$ORDER_PROVIDER_ARN" ] || [ -z "$ISSUE_PROVIDER_ARN" ]; then
    if [ -f "$SCRIPT_DIR/create-api-key-providers.sh" ]; then
        echo "Running create-api-key-providers.sh..."
        "$SCRIPT_DIR/create-api-key-providers.sh"
        
        # Get ARNs after creation
        ORDER_PROVIDER_ARN=$(aws bedrock-agentcore-control list-api-key-credential-providers \
            --region "$REGION" \
            --query "credentialProviders[?name=='order-management-api-key-provider'].credentialProviderArn" \
            --output text 2>/dev/null | head -n1 || echo "")
        
        ISSUE_PROVIDER_ARN=$(aws bedrock-agentcore-control list-api-key-credential-providers \
            --region "$REGION" \
            --query "credentialProviders[?name=='issue-management-api-key-provider'].credentialProviderArn" \
            --output text 2>/dev/null | head -n1 || echo "")
    else
        # Use environment variables if set
        ORDER_PROVIDER_ARN="${ORDER_MANAGEMENT_API_KEY_PROVIDER_ARN:-$ORDER_PROVIDER_ARN}"
        ISSUE_PROVIDER_ARN="${ISSUE_MANAGEMENT_API_KEY_PROVIDER_ARN:-$ISSUE_PROVIDER_ARN}"
    fi
fi

if [ -z "$ORDER_PROVIDER_ARN" ] || [ -z "$ISSUE_PROVIDER_ARN" ]; then
    echo "Error: API key provider ARNs not found."
    echo "Please create them first using: ./create-api-key-providers.sh"
    echo "Or set environment variables:"
    echo "  ORDER_MANAGEMENT_API_KEY_PROVIDER_ARN"
    echo "  ISSUE_MANAGEMENT_API_KEY_PROVIDER_ARN"
    exit 1
fi

echo "Order Management API Key Provider ARN: $ORDER_PROVIDER_ARN"
echo "Issue Management API Key Provider ARN: $ISSUE_PROVIDER_ARN"
echo ""

# Step 2: Get CloudFront distribution domain
echo "Step 2: Getting CloudFront distribution domain..."
CLOUDFRONT_STACK_NAME="${CLOUDFRONT_STACK_NAME:-customer-support-demo-cloudfront}"
CLOUDFRONT_DOMAIN=$(aws cloudformation describe-stacks \
    --stack-name "$CLOUDFRONT_STACK_NAME" \
    --region "$REGION" \
    --query 'Stacks[0].Outputs[?OutputKey==`CloudFrontURL`].OutputValue' \
    --output text 2>/dev/null || echo "")

if [ -z "$CLOUDFRONT_DOMAIN" ]; then
    echo "Error: Could not get CloudFront domain from stack: $CLOUDFRONT_STACK_NAME"
    exit 1
fi

# Extract domain from URL (remove https:// if present)
CLOUDFRONT_DOMAIN=$(echo "$CLOUDFRONT_DOMAIN" | sed 's|^https://||' | sed 's|/$||')
echo "CloudFront Domain: $CLOUDFRONT_DOMAIN"
echo ""

# Step 3: Get Product Knowledge Base ID
echo "Step 3: Getting Product Knowledge Base ID..."
KB_STACK_NAME="${KB_STACK_NAME:-product-knowledge-base}"
KB_ID=$(aws cloudformation describe-stacks \
    --stack-name "$KB_STACK_NAME" \
    --region "$REGION" \
    --query 'Stacks[0].Outputs[?OutputKey==`KnowledgeBaseId`].OutputValue' \
    --output text 2>/dev/null || echo "")

if [ -z "$KB_ID" ]; then
    echo "Error: Could not get Knowledge Base ID from stack: $KB_STACK_NAME"
    exit 1
fi

echo "Product Knowledge Base ID: $KB_ID"
echo ""

# Step 4: Get OpenAPI schema URIs
echo "Step 4: Getting OpenAPI schema URIs..."
ORDER_SCHEMA_URI="${ORDER_MANAGEMENT_OPENAPI_SCHEMA_URI}"
ISSUE_SCHEMA_URI="${ISSUE_MANAGEMENT_OPENAPI_SCHEMA_URI}"

if [ -z "$ORDER_SCHEMA_URI" ] || [ -z "$ISSUE_SCHEMA_URI" ]; then
    echo "Warning: OpenAPI schema URIs not set in environment."
    echo "Please ensure schemas are uploaded to S3 and set:"
    echo "  ORDER_MANAGEMENT_OPENAPI_SCHEMA_URI"
    echo "  ISSUE_MANAGEMENT_OPENAPI_SCHEMA_URI"
    echo ""
    echo "You can upload them using: ./upload-schemas.sh"
    read -p "Continue anyway? (y/n): " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi

echo "Order Management OpenAPI Schema URI: ${ORDER_SCHEMA_URI:-Not set}"
echo "Issue Management OpenAPI Schema URI: ${ISSUE_SCHEMA_URI:-Not set}"
echo ""

# Step 5: Deploy CloudFormation stack
echo "Step 5: Deploying CloudFormation stack..."
TEMPLATE_FILE="$PROJECT_DIR/manifests/mcp-gateway.yaml"

if [ ! -f "$TEMPLATE_FILE" ]; then
    echo "Error: CloudFormation template not found: $TEMPLATE_FILE"
    exit 1
fi

# Prepare parameters
PARAMETERS=(
    "ParameterKey=Region,ParameterValue=$REGION"
    "ParameterKey=CognitoDomainPrefix,ParameterValue=$COGNITO_DOMAIN_PREFIX"
    "ParameterKey=CloudFrontDistributionDomain,ParameterValue=$CLOUDFRONT_DOMAIN"
    "ParameterKey=ProductKnowledgeBaseId,ParameterValue=$KB_ID"
    "ParameterKey=OrderManagementApiKeyProviderArn,ParameterValue=$ORDER_PROVIDER_ARN"
    "ParameterKey=IssueManagementApiKeyProviderArn,ParameterValue=$ISSUE_PROVIDER_ARN"
)

if [ -n "$ORDER_SCHEMA_URI" ]; then
    PARAMETERS+=("ParameterKey=OrderManagementOpenApiSchemaUri,ParameterValue=$ORDER_SCHEMA_URI")
fi

if [ -n "$ISSUE_SCHEMA_URI" ]; then
    PARAMETERS+=("ParameterKey=IssueManagementOpenApiSchemaUri,ParameterValue=$ISSUE_SCHEMA_URI")
fi

# Check if stack exists
if aws cloudformation describe-stacks --stack-name "$STACK_NAME" --region "$REGION" >/dev/null 2>&1; then
    echo "Stack $STACK_NAME already exists. Updating..."
    OPERATION="update-stack"
    WAIT_CMD="stack-update-complete"
else
    echo "Creating new stack $STACK_NAME..."
    OPERATION="create-stack"
    WAIT_CMD="stack-create-complete"
fi

# Deploy stack
aws cloudformation $OPERATION \
    --stack-name "$STACK_NAME" \
    --template-body "file://$TEMPLATE_FILE" \
    --parameters "${PARAMETERS[@]}" \
    --capabilities CAPABILITY_NAMED_IAM \
    --region "$REGION" \
    --output json

echo ""
echo "Waiting for stack $OPERATION to complete..."
aws cloudformation wait $WAIT_CMD \
    --stack-name "$STACK_NAME" \
    --region "$REGION"

if [ $? -eq 0 ]; then
    echo ""
    echo "=========================================="
    echo "Stack deployed successfully!"
    echo "=========================================="
    echo ""
    
    # Display outputs
    echo "Stack Outputs:"
    aws cloudformation describe-stacks \
        --stack-name "$STACK_NAME" \
        --region "$REGION" \
        --query 'Stacks[0].Outputs[*].[OutputKey,OutputValue,Description]' \
        --output table
    
    echo ""
    echo "=========================================="
    echo "Next Steps:"
    echo "=========================================="
    echo "1. Create a test user in Cognito User Pool"
    echo "2. Obtain JWT token from Cognito"
    echo "3. Test Gateway endpoint with JWT token"
    echo ""
    echo "See README.md for detailed instructions."
    echo ""
else
    echo ""
    echo "Error: Stack deployment failed or timed out"
    echo "Check CloudFormation console for details"
    exit 1
fi
