#!/bin/bash

# Script to test Bedrock Retrieve API with various RAG queries
# Usage: ./test-retrieve.sh

set -e

# Default values
REGION="${REGION:-us-west-2}"
STACK_NAME="${STACK_NAME:-product-knowledge-base}"
KB_NAME="${KB_NAME:-product-knowledge-base}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

echo "=========================================="
echo "Bedrock Retrieve API Test"
echo "=========================================="
echo ""

# Get Knowledge Base ID from CloudFormation stack
KB_ID=$(aws cloudformation describe-stacks \
    --stack-name "$STACK_NAME" \
    --region "$REGION" \
    --query 'Stacks[0].Outputs[?OutputKey==`KnowledgeBaseId`].OutputValue' \
    --output text 2>/dev/null || echo "")

if [ -z "$KB_ID" ]; then
    echo "Error: Could not get Knowledge Base ID from stack"
    exit 1
fi

echo "Knowledge Base ID: $KB_ID"
echo "Region: $REGION"
echo ""

# Define test queries
declare -a QUERIES=(
    "What servers are suitable for edge deployments?"
    "Which server models support GPU acceleration?"
    "What are the specifications for servers with high memory capacity?"
    "Find servers that support virtualization workloads"
    "What servers have NVMe storage options?"
    "Which servers are suitable for HPC or compute-intensive workloads?"
    "What servers support 100GbE networking?"
    "Find servers with AMD EPYC processors"
)

# Function to test a query
test_query() {
    local query="$1"
    local query_num="$2"
    
    echo "----------------------------------------"
    echo "Query $query_num: $query"
    echo "----------------------------------------"
    
    # Call Bedrock Retrieve API
    RESPONSE=$(aws bedrock-agent-runtime retrieve \
        --knowledge-base-id "$KB_ID" \
        --retrieval-query "{\"text\":\"$query\"}" \
        --region "$REGION" \
        --output json 2>&1)
    
    if [ $? -ne 0 ]; then
        echo "Error: Failed to retrieve"
        echo "$RESPONSE"
        echo ""
        return 1
    fi
    
    # Parse and display results
    echo "$RESPONSE" | python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
    retrieval_results = data.get('retrievalResults', [])
    print(f'Found {len(retrieval_results)} results')
    print()
    
    for i, result in enumerate(retrieval_results[:3], 1):  # Show top 3
        score = result.get('score', 0)
        location = result.get('location', {})
        s3_location = location.get('s3Location', {})
        uri = s3_location.get('uri', 'N/A')
        content = result.get('content', {})
        text = content.get('text', 'N/A')
        
        # Extract filename from URI
        filename = uri.split('/')[-1] if '/' in uri else uri
        
        print(f'Result {i} (Score: {score:.4f}):')
        print(f'  Source: {filename}')
        print(f'  Preview: {text[:200]}...')
        print()
except Exception as e:
    print(f'Error parsing response: {e}')
    print('Raw response:')
    print(sys.stdin.read())
"
    
    echo ""
}

# Run all test queries
for i in "${!QUERIES[@]}"; do
    test_query "${QUERIES[$i]}" $((i+1))
    sleep 1  # Small delay between queries
done

echo "=========================================="
echo "Test Complete"
echo "=========================================="
