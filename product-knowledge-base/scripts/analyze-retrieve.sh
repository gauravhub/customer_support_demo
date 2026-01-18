#!/bin/bash

# Detailed analysis script for Bedrock Retrieve API
# Shows product IDs and validates relevance
# Usage: ./analyze-retrieve.sh

set -e

REGION="${REGION:-us-west-2}"
STACK_NAME="${STACK_NAME:-product-knowledge-base}"

# Get Knowledge Base ID
KB_ID=$(aws cloudformation describe-stacks \
    --stack-name "$STACK_NAME" \
    --region "$REGION" \
    --query 'Stacks[0].Outputs[?OutputKey==`KnowledgeBaseId`].OutputValue' \
    --output text 2>/dev/null || echo "")

if [ -z "$KB_ID" ]; then
    echo "Error: Could not get Knowledge Base ID"
    exit 1
fi

# Test specific queries with expected results
test_detailed_query() {
    local query="$1"
    local expected_products="$2"  # Comma-separated list of expected product IDs
    
    echo "=========================================="
    echo "Query: $query"
    echo "Expected products: $expected_products"
    echo "=========================================="
    
    RESPONSE=$(aws bedrock-agent-runtime retrieve \
        --knowledge-base-id "$KB_ID" \
        --retrieval-query "{\"text\":\"$query\"}" \
        --region "$REGION" \
        --output json 2>&1)
    
    if [ $? -ne 0 ]; then
        echo "Error: Failed to retrieve"
        echo "$RESPONSE"
        return 1
    fi
    
    # Parse and display detailed results
    echo "$RESPONSE" | python3 -c "
import sys, json

query = '$query'
expected = '$expected_products'.split(',') if '$expected_products' else []

try:
    data = json.load(sys.stdin)
    results = data.get('retrievalResults', [])
    
    print(f'\\nFound {len(results)} results:\\n')
    
    found_products = []
    for i, result in enumerate(results, 1):
        score = result.get('score', 0)
        location = result.get('location', {})
        s3_location = location.get('s3Location', {})
        uri = s3_location.get('uri', '')
        
        # Extract product ID from filename
        filename = uri.split('/')[-1] if '/' in uri else uri
        product_id = filename.replace('.json', '').upper()
        found_products.append(product_id)
        
        content = result.get('content', {})
        text = content.get('text', '')
        
        # Try to extract product_id from content
        import re
        product_match = re.search(r'\"product_id\"\s*:\s*\"([^\"]+)\"', text)
        if product_match:
            product_id = product_match.group(1)
        
        # Extract model/brand from content
        model_match = re.search(r'\"model\"\s*:\s*\"([^\"]+)\"', text)
        model = model_match.group(1) if model_match else 'N/A'
        
        brand_match = re.search(r'\"brand\"\s*:\s*\"([^\"]+)\"', text)
        brand = brand_match.group(1) if brand_match else 'N/A'
        
        print(f'{i}. {product_id} - {brand} {model} (Score: {score:.4f})')
        
        # Show relevant snippet
        snippet = text[:300].replace('\\n', ' ')
        print(f'   Snippet: {snippet}...')
        print()
    
    # Validation
    print('\\n--- Validation ---')
    if expected:
        expected_set = set([e.strip().upper() for e in expected if e.strip()])
        found_set = set([f.upper() for f in found_products[:3]])  # Top 3
        
        matches = expected_set.intersection(found_set)
        if matches:
            print(f'✓ Found expected products: {sorted(matches)}')
        else:
            print(f'✗ Expected products not in top results')
            print(f'  Expected: {sorted(expected_set)}')
            print(f'  Found (top 3): {sorted(found_set)}')
    else:
        print('No expected products specified for validation')
    
except Exception as e:
    print(f'Error: {e}')
    import traceback
    traceback.print_exc()
"
    
    echo ""
}

# Run detailed tests with expected results
echo "=========================================="
echo "Detailed RAG Query Analysis"
echo "=========================================="
echo "Knowledge Base ID: $KB_ID"
echo ""

# Test 1: Edge deployments - should return SRV-0001, SRV-0008
test_detailed_query \
    "What servers are suitable for edge deployments?" \
    "SRV-0001,SRV-0008"

# Test 2: GPU support - should return SRV-0004, SRV-0009
test_detailed_query \
    "Which server models support GPU acceleration?" \
    "SRV-0004,SRV-0009"

# Test 3: High memory - should return SRV-0002, SRV-0005, SRV-0007
test_detailed_query \
    "What are the specifications for servers with high memory capacity over 2TB?" \
    "SRV-0002,SRV-0005,SRV-0007"

# Test 4: Virtualization - should return SRV-0002, SRV-0007
test_detailed_query \
    "Find servers that support virtualization workloads" \
    "SRV-0002,SRV-0007"

# Test 5: AMD EPYC - should return SRV-0005
test_detailed_query \
    "Find servers with AMD EPYC processors" \
    "SRV-0005"

# Test 6: Blade servers - should return SRV-0005
test_detailed_query \
    "What blade server models are available?" \
    "SRV-0005"

echo "=========================================="
echo "Analysis Complete"
echo "=========================================="
