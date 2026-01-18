#!/bin/bash

# Script to set up OpenSearch role mapping for Bedrock KB
# This maps the IAM role to an OpenSearch role with necessary permissions
# Usage: ./setup-opensearch-role.sh

set -e

# Default values
REGION="${REGION:-us-west-2}"
SHARED_STACK_NAME="${SHARED_STACK_NAME:-customer-support-demo-bedrock-kb}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

echo "=========================================="
echo "Setup OpenSearch Role Mapping"
echo "=========================================="
echo ""

# Get values from shared infrastructure
OPENSEARCH_DOMAIN_ENDPOINT=$(aws cloudformation describe-stacks \
    --stack-name "$SHARED_STACK_NAME" \
    --region "$REGION" \
    --query 'Stacks[0].Outputs[?OutputKey==`OpenSearchDomainEndpoint`].OutputValue' \
    --output text 2>/dev/null || echo "")

OPENSEARCH_ADMIN_USER_SECRET_ARN=$(aws cloudformation describe-stacks \
    --stack-name "$SHARED_STACK_NAME" \
    --region "$REGION" \
    --query 'Stacks[0].Outputs[?OutputKey==`OpenSearchAdminUserSecretArn`].OutputValue' \
    --output text 2>/dev/null || echo "")

BEDROCK_KB_ROLE_ARN=$(aws cloudformation describe-stacks \
    --stack-name "$SHARED_STACK_NAME" \
    --region "$REGION" \
    --query 'Stacks[0].Outputs[?OutputKey==`BedrockKBRoleArn`].OutputValue' \
    --output text 2>/dev/null || echo "")

if [ -z "$OPENSEARCH_DOMAIN_ENDPOINT" ] || [ -z "$OPENSEARCH_ADMIN_USER_SECRET_ARN" ] || [ -z "$BEDROCK_KB_ROLE_ARN" ]; then
    echo "Error: Could not get required values from shared infrastructure stack"
    exit 1
fi

# Get credentials from Secrets Manager
echo "Getting OpenSearch credentials..."
ADMIN_CREDS=$(aws secretsmanager get-secret-value \
    --secret-id "$OPENSEARCH_ADMIN_USER_SECRET_ARN" \
    --region "$REGION" \
    --query 'SecretString' \
    --output text)

OPENSEARCH_USER=$(echo "$ADMIN_CREDS" | python3 -c "import sys, json; print(json.load(sys.stdin)['username'])")
OPENSEARCH_PASSWORD=$(echo "$ADMIN_CREDS" | python3 -c "import sys, json; print(json.load(sys.stdin)['password'])")

OPENSEARCH_URL="https://${OPENSEARCH_DOMAIN_ENDPOINT}"

echo "OpenSearch Endpoint: $OPENSEARCH_URL"
echo "Bedrock KB Role ARN: $BEDROCK_KB_ROLE_ARN"
echo ""

# Create OpenSearch role for Bedrock KB
ROLE_NAME="bedrock_kb_role"
echo "Creating OpenSearch role: $ROLE_NAME"

# Create role with necessary permissions
curl -X PUT "${OPENSEARCH_URL}/_plugins/_security/api/roles/${ROLE_NAME}" \
  -u "${OPENSEARCH_USER}:${OPENSEARCH_PASSWORD}" \
  -H "Content-Type: application/json" \
  -d '{
    "cluster_permissions": [
      "cluster_composite_ops",
      "cluster_monitor"
    ],
    "index_permissions": [
      {
        "index_patterns": ["*"],
        "dls": "",
        "fls": [],
        "masked_fields": [],
        "allowed_actions": [
          "indices_all"
        ]
      }
    ],
    "tenant_permissions": []
  }' \
  --insecure \
  -s -o /dev/null -w "%{http_code}"

echo ""

# Map IAM role to OpenSearch role
echo "Mapping IAM role to OpenSearch role..."
curl -X PUT "${OPENSEARCH_URL}/_plugins/_security/api/rolesmapping/${ROLE_NAME}" \
  -u "${OPENSEARCH_USER}:${OPENSEARCH_PASSWORD}" \
  -H "Content-Type: application/json" \
  -d "{
    \"backend_roles\": [\"${BEDROCK_KB_ROLE_ARN}\"],
    \"hosts\": [],
    \"users\": []
  }" \
  --insecure \
  -s -o /dev/null -w "%{http_code}"

echo ""
echo "✓ OpenSearch role mapping configured"
echo ""
