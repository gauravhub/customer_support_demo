#!/bin/bash

# Script to start ingestion job for Product Knowledge Base
# Usage: ./start-ingestion.sh

set -e

# Default values
REGION="${REGION:-us-west-2}"
STACK_NAME="${STACK_NAME:-product-knowledge-base}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "=========================================="
echo "Start Ingestion Job"
echo "=========================================="
echo "Stack Name: $STACK_NAME"
echo "Region: $REGION"
echo "=========================================="
echo ""

# Get values from CloudFormation stack
KB_ID=$(aws cloudformation describe-stacks \
    --stack-name "$STACK_NAME" \
    --region "$REGION" \
    --query 'Stacks[0].Outputs[?OutputKey==`KnowledgeBaseId`].OutputValue' \
    --output text 2>/dev/null || echo "")

DATA_SOURCE_ID=$(aws cloudformation describe-stacks \
    --stack-name "$STACK_NAME" \
    --region "$REGION" \
    --query 'Stacks[0].Outputs[?OutputKey==`DataSourceId`].OutputValue' \
    --output text 2>/dev/null || echo "")

if [ -z "$KB_ID" ] || [ -z "$DATA_SOURCE_ID" ]; then
    echo "Error: Could not get Knowledge Base ID or Data Source ID from stack: $STACK_NAME"
    echo "Please ensure the stack is deployed first."
    exit 1
fi

echo "Knowledge Base ID: $KB_ID"
echo "Data Source ID: $DATA_SOURCE_ID"
echo ""

# Start ingestion job
echo "Starting ingestion job..."
JOB_ID=$(aws bedrock-agent start-ingestion-job \
    --knowledge-base-id "$KB_ID" \
    --data-source-id "$DATA_SOURCE_ID" \
    --region "$REGION" \
    --query 'ingestionJob.ingestionJobId' \
    --output text)

echo "✓ Ingestion job started: $JOB_ID"
echo ""
echo "Monitor job status with:"
echo "  aws bedrock-agent get-ingestion-job \\"
echo "    --knowledge-base-id $KB_ID \\"
echo "    --data-source-id $DATA_SOURCE_ID \\"
echo "    --ingestion-job-id $JOB_ID \\"
echo "    --region $REGION"
echo ""
