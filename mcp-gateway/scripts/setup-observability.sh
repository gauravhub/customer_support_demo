#!/bin/bash
# Enable CloudWatch Logs and X-Ray tracing for AgentCore Gateway
# Uses CloudWatch Logs delivery sources and destinations

set -e

REGION="${REGION:-us-west-2}"
STACK_NAME="${STACK_NAME:-customer-support-demo-mcp-gateway}"
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)

echo "=========================================="
echo "Enabling Observability for Gateway"
echo "=========================================="
echo ""

# Get Gateway ID
GATEWAY_ID=$(aws cloudformation describe-stacks \
    --stack-name "$STACK_NAME" \
    --region "$REGION" \
    --query 'Stacks[0].Outputs[?OutputKey==`GatewayId`].OutputValue' \
    --output text)

if [ -z "$GATEWAY_ID" ]; then
    echo "Error: Could not get Gateway ID"
    exit 1
fi

GATEWAY_ARN="arn:aws:bedrock-agentcore:${REGION}:${ACCOUNT_ID}:gateway/${GATEWAY_ID}"
LOG_GROUP="/aws/vendedlogs/bedrock-agentcore/gateway/APPLICATION_LOGS/${GATEWAY_ID}"

echo "Gateway ID: $GATEWAY_ID"
echo "Gateway ARN: $GATEWAY_ARN"
echo "Log Group: $LOG_GROUP"
echo ""

# 1. Create log group
echo "Step 1: Creating CloudWatch Log Group..."
aws logs create-log-group \
    --log-group-name "$LOG_GROUP" \
    --region "$REGION" 2>/dev/null || echo "  Log group already exists"
echo "✓ Log group ready"
echo ""

# 2. Set exception level to DEBUG
echo "Step 2: Setting exception level to DEBUG..."
# Get current gateway config
CURRENT_CONFIG=$(aws bedrock-agentcore-control get-gateway \
    --gateway-identifier "$GATEWAY_ID" \
    --region "$REGION" \
    --output json)

GATEWAY_NAME=$(echo "$CURRENT_CONFIG" | python3 -c "import sys, json; print(json.load(sys.stdin)['name'])")
ROLE_ARN=$(echo "$CURRENT_CONFIG" | python3 -c "import sys, json; print(json.load(sys.stdin)['roleArn'])")
PROTOCOL_TYPE=$(echo "$CURRENT_CONFIG" | python3 -c "import sys, json; print(json.load(sys.stdin)['protocolType'])")
AUTHORIZER_TYPE=$(echo "$CURRENT_CONFIG" | python3 -c "import sys, json; print(json.load(sys.stdin)['authorizerType'])")

# Update with DEBUG exception level
aws bedrock-agentcore-control update-gateway \
    --gateway-identifier "$GATEWAY_ID" \
    --name "$GATEWAY_NAME" \
    --role-arn "$ROLE_ARN" \
    --protocol-type "$PROTOCOL_TYPE" \
    --authorizer-type "$AUTHORIZER_TYPE" \
    --exception-level DEBUG \
    --region "$REGION" > /dev/null 2>&1 || echo "  Exception level may already be set"
echo "✓ Exception level set to DEBUG"
echo ""

# 3. Create delivery source for APPLICATION_LOGS
echo "Step 3: Creating delivery source for APPLICATION_LOGS..."
SOURCE_NAME="${GATEWAY_ID}-logs-source"
aws logs put-delivery-source \
    --name "$SOURCE_NAME" \
    --log-type APPLICATION_LOGS \
    --resource-arn "$GATEWAY_ARN" \
    --region "$REGION" 2>/dev/null || echo "  Delivery source may already exist"
echo "✓ Delivery source created"
echo ""

# 4. Create delivery destination for CloudWatch Logs
echo "Step 4: Creating delivery destination for CloudWatch Logs..."
DEST_NAME="${GATEWAY_ID}-logs-destination"
LOG_GROUP_ARN="arn:aws:logs:${REGION}:${ACCOUNT_ID}:log-group:${LOG_GROUP}"

aws logs put-delivery-destination \
    --name "$DEST_NAME" \
    --delivery-destination-type CWL \
    --delivery-destination-configuration "destinationResourceArn=${LOG_GROUP_ARN}" \
    --region "$REGION" 2>/dev/null || echo "  Delivery destination may already exist"
echo "✓ Delivery destination created"
echo ""

# 5. Create delivery (connect source to destination)
echo "Step 5: Creating delivery (connecting source to destination)..."
DEST_ARN=$(aws logs describe-delivery-destinations \
    --region "$REGION" \
    --query "deliveryDestinations[?name=='$DEST_NAME'].arn" \
    --output text 2>/dev/null | head -1)

if [ -n "$DEST_ARN" ]; then
    aws logs create-delivery \
        --delivery-source-name "$SOURCE_NAME" \
        --delivery-destination-arn "$DEST_ARN" \
        --region "$REGION" 2>/dev/null || echo "  Delivery may already exist"
    echo "✓ Delivery created"
else
    echo "  Warning: Could not find destination ARN"
fi
echo ""

# 6. Enable X-Ray tracing (optional but recommended)
echo "Step 6: Enabling X-Ray tracing..."
TRACES_SOURCE_NAME="${GATEWAY_ID}-traces-source"
aws logs put-delivery-source \
    --name "$TRACES_SOURCE_NAME" \
    --log-type TRACES \
    --resource-arn "$GATEWAY_ARN" \
    --region "$REGION" 2>/dev/null || echo "  Traces source may already exist"

TRACES_DEST_NAME="${GATEWAY_ID}-traces-destination"
aws logs put-delivery-destination \
    --name "$TRACES_DEST_NAME" \
    --delivery-destination-type XRAY \
    --region "$REGION" 2>/dev/null || echo "  Traces destination may already exist"

TRACES_DEST_ARN=$(aws logs describe-delivery-destinations \
    --region "$REGION" \
    --query "deliveryDestinations[?name=='$TRACES_DEST_NAME'].arn" \
    --output text 2>/dev/null | head -1)

if [ -n "$TRACES_DEST_ARN" ]; then
    aws logs create-delivery \
        --delivery-source-name "$TRACES_SOURCE_NAME" \
        --delivery-destination-arn "$TRACES_DEST_ARN" \
        --region "$REGION" 2>/dev/null || echo "  Traces delivery may already exist"
    echo "✓ X-Ray tracing enabled"
fi
echo ""

echo "=========================================="
echo "Observability Setup Complete"
echo "=========================================="
echo ""
echo "Log Group: $LOG_GROUP"
echo "View logs:"
echo "  aws logs tail '$LOG_GROUP' --follow --region $REGION"
echo ""
echo "View traces:"
echo "  CloudWatch Console → Transaction Search → /aws/spans/default"
echo ""

# Wait a moment for logs to start flowing
echo "Waiting 10 seconds for logs to start flowing..."
sleep 10

# Check for recent logs
echo ""
echo "Checking for recent log streams..."
aws logs describe-log-streams \
    --log-group-name "$LOG_GROUP" \
    --region "$REGION" \
    --order-by LastEventTime \
    --descending \
    --max-items 3 \
    --query 'logStreams[*].[logStreamName, lastEventTimestamp]' \
    --output table 2>/dev/null || echo "No log streams yet. Logs will appear after Gateway activity."
