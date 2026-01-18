#!/bin/bash

# Script to create OpenSearch vector index for Bedrock KB
# Usage: ./create-opensearch-index.sh

set -e

# Default values
REGION="${REGION:-us-west-2}"
SHARED_STACK_NAME="${SHARED_STACK_NAME:-customer-support-demo-bedrock-kb}"
KB_NAME="${KB_NAME:-product-knowledge-base}"
INDEX_NAME="${KB_NAME}-index"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

echo "=========================================="
echo "Create OpenSearch Vector Index"
echo "=========================================="
echo "Index Name: $INDEX_NAME"
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

if [ -z "$OPENSEARCH_DOMAIN_ENDPOINT" ] || [ -z "$OPENSEARCH_ADMIN_USER_SECRET_ARN" ]; then
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
echo ""

# Check if index already exists
echo "Checking if index exists..."
HTTP_CODE=$(curl -X HEAD "${OPENSEARCH_URL}/${INDEX_NAME}" \
  -u "${OPENSEARCH_USER}:${OPENSEARCH_PASSWORD}" \
  --insecure \
  -s -o /dev/null -w "%{http_code}" || echo "404")

if [ "$HTTP_CODE" = "200" ]; then
    echo "Index $INDEX_NAME already exists. Deleting to recreate with FAISS..."
    curl -X DELETE "${OPENSEARCH_URL}/${INDEX_NAME}" \
      -u "${OPENSEARCH_USER}:${OPENSEARCH_PASSWORD}" \
      --insecure \
      -s -o /dev/null
    echo "Deleted existing index."
    sleep 2
fi

# Create vector index
echo "Creating vector index: $INDEX_NAME"
echo ""

# Create index with vector field mapping
# Using k-NN plugin for vector search (OpenSearch 2.x) with FAISS engine
RESPONSE=$(curl -X PUT "${OPENSEARCH_URL}/${INDEX_NAME}" \
  -u "${OPENSEARCH_USER}:${OPENSEARCH_PASSWORD}" \
  -H "Content-Type: application/json" \
  -d "{
    \"settings\": {
      \"index\": {
        \"knn\": true,
        \"knn.algo_param.ef_search\": 100
      }
    },
    \"mappings\": {
      \"properties\": {
        \"vector\": {
          \"type\": \"knn_vector\",
          \"dimension\": 1536,
          \"method\": {
            \"name\": \"hnsw\",
            \"space_type\": \"innerproduct\",
            \"engine\": \"faiss\",
            \"parameters\": {
              \"ef_construction\": 128,
              \"m\": 24
            }
          }
        },
        \"text\": {
          \"type\": \"text\"
        }
      }
    }
  }" \
  --insecure \
  -s -w "\n%{http_code}")

HTTP_CODE=$(echo "$RESPONSE" | tail -n1)
BODY=$(echo "$RESPONSE" | head -n-1)

if [ "$HTTP_CODE" = "200" ] || [ "$HTTP_CODE" = "201" ]; then
    echo "✓ Index created successfully: $INDEX_NAME"
else
    echo "Error: Failed to create index (HTTP $HTTP_CODE)"
    echo "Response: $BODY"
    exit 1
fi

echo ""
