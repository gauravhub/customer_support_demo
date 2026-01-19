#!/bin/bash

# Script to upload OpenAPI schemas to S3 for Gateway targets
# 
# This script processes OpenAPI specs and replaces hardcoded values before uploading:
#   - CloudFront distribution domain
#   - AWS Account ID
#   - AWS Region
#
# Usage:
#   # Option 1: Auto-detect S3 bucket from shared-infra/bedrock-kb (recommended)
#   ./upload-schemas.sh
#
#   # Option 2: Manually specify bucket
#   export S3_BUCKET_NAME=customer-support-kb-datasources-{ACCOUNT_ID}
#   ./upload-schemas.sh
#
# The script will:
#   1. Auto-detect S3 bucket from customer-support-demo-bedrock-kb stack (or use provided)
#   2. Fetch CloudFront domain from CloudFormation stack (if not provided)
#   3. Fetch AWS Account ID from STS
#   4. Create temporary copies of OpenAPI files
#   5. Replace hardcoded values with current values
#   6. Upload modified files to S3
#

set -e

# Default values
REGION="${REGION:-us-west-2}"
S3_PREFIX="${S3_PREFIX:-api-schemas/}"
CLOUDFRONT_DOMAIN="${CLOUDFRONT_DOMAIN:-}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

echo "=========================================="
echo "Upload OpenAPI Schemas to S3"
echo "=========================================="
echo ""

# Get AWS Account ID
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text 2>/dev/null || echo "ACCOUNT_ID_PLACEHOLDER")

# Auto-detect or validate S3 bucket
if [ -z "$S3_BUCKET_NAME" ]; then
    echo "S3_BUCKET_NAME not set, attempting to auto-detect from shared-infra/bedrock-kb stack..."
    S3_BUCKET_NAME=$(aws cloudformation describe-stacks \
        --stack-name customer-support-demo-bedrock-kb \
        --region "$REGION" \
        --query 'Stacks[0].Outputs[?OutputKey==`S3BucketName`].OutputValue' \
        --output text 2>/dev/null)
    
    if [ -z "$S3_BUCKET_NAME" ] || [ "$S3_BUCKET_NAME" = "None" ]; then
        echo "Could not auto-detect S3 bucket from CloudFormation."
        echo "Trying default naming pattern: customer-support-kb-datasources-{ACCOUNT_ID}"
        S3_BUCKET_NAME="customer-support-kb-datasources-${ACCOUNT_ID}"
    else
        echo "✓ Auto-detected S3 bucket: $S3_BUCKET_NAME"
    fi
fi

# Verify bucket exists
echo "Verifying S3 bucket access..."
if ! aws s3 ls "s3://$S3_BUCKET_NAME" --region "$REGION" >/dev/null 2>&1; then
    echo ""
    echo "Error: S3 bucket '$S3_BUCKET_NAME' not found or not accessible"
    echo ""
    echo "Please ensure:"
    echo "  1. shared-infra/bedrock-kb stack is deployed"
    echo "  2. S3 bucket exists: customer-support-kb-datasources-{ACCOUNT_ID}"
    echo "  3. You have access to the bucket in region: $REGION"
    echo ""
    echo "Or manually set: export S3_BUCKET_NAME=your-bucket-name"
    exit 1
fi
echo "✓ S3 bucket access verified"
echo ""

echo "AWS Account ID: $ACCOUNT_ID"
echo "AWS Region: $REGION"
echo "S3 Bucket: $S3_BUCKET_NAME"
echo "S3 Prefix: $S3_PREFIX"
echo ""

# Get CloudFront distribution domain if not provided
if [ -z "$CLOUDFRONT_DOMAIN" ]; then
    echo "Fetching CloudFront distribution domain from CloudFormation..."
    CLOUDFRONT_DOMAIN=$(aws cloudformation describe-stacks \
        --stack-name customer-support-demo-cloudfront \
        --region "$REGION" \
        --query 'Stacks[0].Outputs[?OutputKey==`CloudFrontURL`].OutputValue' \
        --output text 2>/dev/null)
    
    if [ -z "$CLOUDFRONT_DOMAIN" ] || [ "$CLOUDFRONT_DOMAIN" = "None" ]; then
        echo "⚠ Warning: Could not fetch CloudFront domain from CloudFormation"
        echo "OpenAPI specs will not have CloudFront URLs updated"
    else
        # Extract domain from URL (remove https:// if present)
        CLOUDFRONT_DOMAIN=$(echo "$CLOUDFRONT_DOMAIN" | sed 's|^https://||' | sed 's|/$||')
        echo "CloudFront Domain: $CLOUDFRONT_DOMAIN"
    fi
else
    echo "CloudFront Domain: $CLOUDFRONT_DOMAIN (from environment)"
fi
echo ""

# Create temp directory for modified schemas
TEMP_DIR=$(mktemp -d)
trap "rm -rf $TEMP_DIR" EXIT

# Upload Order Management OpenAPI spec
ORDER_OPENAPI_SOURCE="$PROJECT_DIR/../order-management-api/data/openapi.json"
if [ -f "$ORDER_OPENAPI_SOURCE" ]; then
    echo "Processing Order Management OpenAPI spec..."
    ORDER_OPENAPI_TEMP="$TEMP_DIR/order-management-openapi.json"
    cp "$ORDER_OPENAPI_SOURCE" "$ORDER_OPENAPI_TEMP"
    
    # Replace placeholders
    echo "  → Updating Account ID to: $ACCOUNT_ID"
    sed -i "s/YOUR_ACCOUNT_ID/$ACCOUNT_ID/g" "$ORDER_OPENAPI_TEMP"
    
    echo "  → Updating Region to: $REGION"
    sed -i "s/YOUR_REGION/$REGION/g" "$ORDER_OPENAPI_TEMP"
    
    # Replace CloudFront domain if available
    if [ -n "$CLOUDFRONT_DOMAIN" ]; then
        echo "  → Updating CloudFront domain to: $CLOUDFRONT_DOMAIN"
        sed -i "s|https://[^/]*.cloudfront.net/order-management|https://$CLOUDFRONT_DOMAIN/order-management|g" "$ORDER_OPENAPI_TEMP"
        sed -i "s|YOUR_CLOUDFRONT_DOMAIN|$CLOUDFRONT_DOMAIN|g" "$ORDER_OPENAPI_TEMP"
    fi
    
    # Upload to S3
    echo "  → Uploading to S3..."
    aws s3 cp "$ORDER_OPENAPI_TEMP" \
        "s3://$S3_BUCKET_NAME/${S3_PREFIX}order-management-openapi.json" \
        --region "$REGION"
    echo "✓ Uploaded: s3://$S3_BUCKET_NAME/${S3_PREFIX}order-management-openapi.json"
    echo ""
else
    echo "⚠ Warning: Order Management OpenAPI spec not found at $ORDER_OPENAPI_SOURCE"
    echo ""
fi

# Upload Issue Management OpenAPI spec
ISSUE_OPENAPI_SOURCE="$PROJECT_DIR/../issue-management-api/data/openapi.json"
if [ -f "$ISSUE_OPENAPI_SOURCE" ]; then
    echo "Processing Issue Management OpenAPI spec..."
    ISSUE_OPENAPI_TEMP="$TEMP_DIR/issue-management-openapi.json"
    cp "$ISSUE_OPENAPI_SOURCE" "$ISSUE_OPENAPI_TEMP"
    
    # Replace placeholders
    echo "  → Updating Account ID to: $ACCOUNT_ID"
    sed -i "s/YOUR_ACCOUNT_ID/$ACCOUNT_ID/g" "$ISSUE_OPENAPI_TEMP"
    
    echo "  → Updating Region to: $REGION"
    sed -i "s/YOUR_REGION/$REGION/g" "$ISSUE_OPENAPI_TEMP"
    
    # Replace CloudFront domain if available
    if [ -n "$CLOUDFRONT_DOMAIN" ]; then
        echo "  → Updating CloudFront domain to: $CLOUDFRONT_DOMAIN"
        sed -i "s|https://[^/]*.cloudfront.net/issue-management|https://$CLOUDFRONT_DOMAIN/issue-management|g" "$ISSUE_OPENAPI_TEMP"
        sed -i "s|YOUR_CLOUDFRONT_DOMAIN|$CLOUDFRONT_DOMAIN|g" "$ISSUE_OPENAPI_TEMP"
    fi
    
    # Upload to S3
    echo "  → Uploading to S3..."
    aws s3 cp "$ISSUE_OPENAPI_TEMP" \
        "s3://$S3_BUCKET_NAME/${S3_PREFIX}issue-management-openapi.json" \
        --region "$REGION"
    echo "✓ Uploaded: s3://$S3_BUCKET_NAME/${S3_PREFIX}issue-management-openapi.json"
    echo ""
else
    echo "⚠ Warning: Issue Management OpenAPI spec not found at $ISSUE_OPENAPI_SOURCE"
    echo ""
fi

# Upload Bedrock Agent Runtime Smithy schema (Retrieve-only)
SMITHY_SOURCE="/tmp/bedrock-agent-runtime-retrieve-only.json"
if [ -f "$SMITHY_SOURCE" ]; then
    echo "Uploading Bedrock Agent Runtime Smithy schema (Retrieve-only)..."
    aws s3 cp "$SMITHY_SOURCE" \
        "s3://$S3_BUCKET_NAME/${S3_PREFIX}bedrock-agent-runtime-retrieve-only.json" \
        --region "$REGION"
    echo "✓ Uploaded: s3://$S3_BUCKET_NAME/${S3_PREFIX}bedrock-agent-runtime-retrieve-only.json"
    echo ""
else
    echo "⚠ Warning: Bedrock Smithy schema not found at $SMITHY_SOURCE"
    echo "This schema should have been created during mcp-gateway setup."
    echo ""
fi

echo "=========================================="
echo "Schemas Uploaded Successfully"
echo "=========================================="
echo ""
echo "Export these URIs for CloudFormation:"
echo ""
echo "export ORDER_MANAGEMENT_OPENAPI_SCHEMA_URI=\"s3://$S3_BUCKET_NAME/${S3_PREFIX}order-management-openapi.json\""
echo "export ISSUE_MANAGEMENT_OPENAPI_SCHEMA_URI=\"s3://$S3_BUCKET_NAME/${S3_PREFIX}issue-management-openapi.json\""
echo "export BEDROCK_AGENT_RUNTIME_SMITHY_SCHEMA_URI=\"s3://$S3_BUCKET_NAME/${S3_PREFIX}bedrock-agent-runtime-retrieve-only.json\""
echo ""
