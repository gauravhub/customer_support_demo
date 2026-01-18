# MCP Gateway

AgentCore Gateway with MCP protocol exposing three targets:
- **Order Management API** - API Key authentication
- **Issue Management API** - API Key authentication
- **Product Knowledge Base** - IAM authentication

The MCP endpoint is secured using Amazon Cognito with JWT-based authentication.

## Overview

This component creates:
- **Cognito User Pool** - For JWT-based authentication to the Gateway
- **AgentCore Gateway** - MCP protocol endpoint
- **IAM Role** - For Gateway to access Bedrock Knowledge Base
- **Three Gateway Targets** - Order Management, Issue Management, and Product Knowledge Base

## Architecture

```
┌─────────────────────────────────────────┐
│      AgentCore Gateway (MCP)           │
│      Cognito JWT Authorizer              │
└──────────────┬──────────────────────────┘
               │
        ┌──────┼──────┐
        │      │      │
        ▼      ▼      ▼
   Order API  Issue  Product
   (API Key)  (API   KB (IAM)
              Key)
```

## Prerequisites

**IMPORTANT**: Deploy components in this order:

1. **Shared Infrastructure** (`shared-infra/`)
   - `bedrock-kb` - Creates S3 bucket for data sources ✅ Required
   - `cloudfront` - Creates CloudFront distribution ✅ Required
   - `eks-cluster` - Creates EKS cluster for APIs ✅ Required

2. **APIs** (can be deployed in parallel)
   - `order-management-api` - REST API for order data
   - `issue-management-api` - REST API for JIRA issues

3. **Knowledge Base** (`product-knowledge-base/`)
   - Uses S3 bucket from `shared-infra/bedrock-kb`
   - Creates Bedrock Knowledge Base resource

4. **MCP Gateway** (`mcp-gateway/` - this component)
   - Uses S3 bucket from `shared-infra/bedrock-kb` for OpenAPI schemas
   - Uses CloudFront from `shared-infra/cloudfront`
   - Uses Knowledge Base ID from `product-knowledge-base`

**Note**: The S3 bucket `customer-support-kb-datasources-{ACCOUNT_ID}` is created by `shared-infra/bedrock-kb` and shared by both `product-knowledge-base` and `mcp-gateway`

## Structure

```
mcp-gateway/
├── manifests/
│   └── mcp-gateway.yaml          # CloudFormation template
├── scripts/
│   ├── create-api-key-providers.sh         # Create API key providers (pre-CFN)
│   ├── upload-schemas.sh                   # Upload OpenAPI specs to S3
│   ├── create-gateway.sh                   # Deploy CloudFormation stack
│   ├── delete-gateway.sh                   # Delete stack
│   ├── setup-observability.sh              # Setup CloudWatch logs & X-Ray (post-deploy)
│   └── test-gateway.py                     # Comprehensive test script
└── README.md                                # This file
```

## Deployment Steps

### Step 1: Create API Key Providers

API key providers must be created BEFORE deploying the CloudFormation stack:

```bash
./scripts/create-api-key-providers.sh
```

This creates two API key credential providers:
- `order-management-api-key-provider` (stores API key: `ZGV2LWtleS0xMjM0NQ==`)
- `issue-management-api-key-provider` (stores API key: `cHJvZC1rZXktNjc4OTA=`)

The script will output the provider ARNs. Export them:

```bash
export ORDER_MANAGEMENT_API_KEY_PROVIDER_ARN="<arn-from-output>"
export ISSUE_MANAGEMENT_API_KEY_PROVIDER_ARN="<arn-from-output>"
```

### Step 2: Upload OpenAPI Schemas to S3

Upload the OpenAPI specs to S3 so the Gateway can access them:

```bash
# Option 1: Auto-detect S3 bucket from shared-infra/bedrock-kb stack (recommended)
./scripts/upload-schemas.sh

# Option 2: Manually specify S3 bucket
export S3_BUCKET_NAME="customer-support-kb-datasources-YOUR_ACCOUNT_ID"
./scripts/upload-schemas.sh
```

The `upload-schemas.sh` script automatically:
- **Auto-detects S3 bucket** from `customer-support-demo-bedrock-kb` CloudFormation stack
- Fetches current AWS Account ID from STS
- Fetches AWS Region from environment (defaults to `us-west-2`)
- Fetches CloudFront domain from CloudFormation stack
- Replaces `YOUR_CLOUDFRONT_DOMAIN`, `YOUR_ACCOUNT_ID`, and `YOUR_REGION` placeholders in OpenAPI specs
- Uploads processed schemas to S3 at `api-schemas/` prefix

The script will output S3 URIs. Export them (or let `create-gateway.sh` auto-detect them):

```bash
export ORDER_MANAGEMENT_OPENAPI_SCHEMA_URI="s3://customer-support-kb-datasources-{ACCOUNT_ID}/api-schemas/order-management-openapi.json"
export ISSUE_MANAGEMENT_OPENAPI_SCHEMA_URI="s3://customer-support-kb-datasources-{ACCOUNT_ID}/api-schemas/issue-management-openapi.json"
export BEDROCK_AGENT_RUNTIME_SMITHY_SCHEMA_URI="s3://customer-support-kb-datasources-{ACCOUNT_ID}/api-schemas/bedrock-agent-runtime-retrieve-only.json"
```

**Environment Variables:**
- `S3_BUCKET_NAME` (optional) - S3 bucket name (auto-detected from `customer-support-demo-bedrock-kb` stack if not set)
- `CLOUDFRONT_DOMAIN` (optional) - CloudFront distribution domain (auto-detected from `customer-support-demo-cloudfront` stack)
- `REGION` (optional) - AWS region (defaults to `us-west-2`)
- `S3_PREFIX` (optional) - S3 prefix for schemas (defaults to `api-schemas/`)

**Note**: 
- The S3 bucket is the same one created by `shared-infra/bedrock-kb` and used by `product-knowledge-base`
- Original OpenAPI files in the repository are not modified - all replacements are done on temporary copies

### Step 3: Deploy Gateway

Deploy the CloudFormation stack:

```bash
./scripts/create-gateway.sh
```

The script will:
1. Check/create API key providers (if not already done)
2. Get CloudFront distribution domain
3. Get Product Knowledge Base ID
4. Deploy the CloudFormation stack with all resources

**Environment Variables**:
- `REGION` - AWS region (default: `us-west-2`)
- `STACK_NAME` - CloudFormation stack name (default: `customer-support-demo-mcp-gateway`)
- `COGNITO_DOMAIN_PREFIX` - Cognito domain prefix (default: `customer-support-mcp-gateway`)
- `ORDER_MANAGEMENT_API_KEY_PROVIDER_ARN` - API key provider ARN (auto-detected if created via script)
- `ISSUE_MANAGEMENT_API_KEY_PROVIDER_ARN` - API key provider ARN (auto-detected if created via script)
- `ORDER_MANAGEMENT_OPENAPI_SCHEMA_URI` - S3 URI or HTTP URL to OpenAPI spec
- `ISSUE_MANAGEMENT_OPENAPI_SCHEMA_URI` - S3 URI or HTTP URL to OpenAPI spec

## Configuration

### Cognito User Pool

- **Token Expiration**: 24 hours (maximum)
- **OAuth Flows**: `client_credentials`, `authorization_code`
- **Scopes**: `openid`, `profile`, `email`
- **Discovery URL**: `https://cognito-idp.<region>.amazonaws.com/<user_pool_id>/.well-known/openid-configuration`

### Gateway Targets

1. **Order Management API**
   - Type: OpenAPI Schema
   - Authentication: API Key (via AgentCore Identity)
   - Header: `X-API-Key`

2. **Issue Management API**
   - Type: OpenAPI Schema
   - Authentication: API Key (via AgentCore Identity)
   - Header: `X-API-Key`

3. **Product Knowledge Base**
   - Type: Smithy Schema
   - Service: `aws.bedrock.agentruntime#AgentRuntimeService`
   - Operations: `Retrieve` (only - filtered via OperationFilters)
   - Authentication: IAM (Gateway role)

## Using the Gateway

The AgentCore Gateway exposes an MCP (Model Context Protocol) endpoint that can be accessed by AI agents and clients. Authentication is handled via Cognito JWT tokens.

### Get Gateway Information

```bash
# Get Gateway URL from stack outputs
GATEWAY_URL=$(aws cloudformation describe-stacks \
    --stack-name customer-support-demo-mcp-gateway \
    --query 'Stacks[0].Outputs[?OutputKey==`GatewayUrl`].OutputValue' \
    --output text)

# Get Cognito Discovery URL for OIDC configuration
DISCOVERY_URL=$(aws cloudformation describe-stacks \
    --stack-name customer-support-demo-mcp-gateway \
    --query 'Stacks[0].Outputs[?OutputKey==`CognitoDiscoveryUrl`].OutputValue' \
    --output text)

echo "Gateway URL: $GATEWAY_URL"
echo "Discovery URL: $DISCOVERY_URL"
```

### Authentication

Clients connecting to the Gateway need to:
1. Obtain a JWT token from Cognito (using OAuth 2.0 flows or direct authentication)
2. Include the token in the `Authorization: Bearer <token>` header when making requests to the Gateway

The Gateway validates the JWT token using the Cognito OIDC discovery endpoint and allows access if the token is valid and matches the configured audience and client ID.

### Testing the Gateway

Use the test script to verify the Gateway is working:

```bash
# Run comprehensive test (auth + list tools + test all tools)
./scripts/test-gateway.py

# With custom stack name or region
STACK_NAME=my-gateway REGION=us-east-1 ./scripts/test-gateway.py
```

The test script will:
1. Authenticate with Cognito using `client_credentials` flow
2. List all available tools exposed by the Gateway
3. Test each tool with sample parameters
4. Display summary of successes/failures
5. Save detailed results to `/tmp/mcp_gateway_test_results.json`

## Observability Setup (Post-Deployment)

After deploying the Gateway, run the observability setup script to enable CloudWatch Logs and X-Ray tracing:

```bash
./scripts/setup-observability.sh
```

This script configures:
1. **CloudWatch Logs** - Application logs from the Gateway
2. **Exception Level** - Sets to DEBUG for detailed logging
3. **Delivery Sources** - Connects Gateway to CloudWatch Logs
4. **X-Ray Tracing** - Enables distributed tracing

**Why a separate script?**
CloudFormation doesn't yet support:
- `AWS::Logs::DeliverySource` (CloudWatch Logs delivery)
- `AWS::Logs::DeliveryDestination` 
- `AWS::Logs::Delivery`
- X-Ray tracing setup for AgentCore
- Gateway exception level updates

These must be configured via AWS CLI API calls after the Gateway is created.

**Note**: The log group itself is created by CloudFormation, but connecting it to the Gateway requires the setup script.

## Stack Outputs

After deployment, the stack provides:

- `GatewayLogGroupName` - CloudWatch Log Group name
- `CognitoUserPoolId` - User Pool ID
- `CognitoUserPoolClientId` - Client ID for authentication
- `CognitoUserPoolClientSecret` - Client secret (for OAuth flows that require it)
- `CognitoDiscoveryUrl` - OIDC discovery URL
- `CognitoTokenEndpoint` - OAuth2 token endpoint URL
- `CognitoResourceServerIdentifier` - Resource server identifier (OAuth scope prefix)
- `GatewayId` - Gateway identifier
- `GatewayArn` - Gateway ARN
- `GatewayUrl` - Gateway endpoint URL

## Cleanup

```bash
# Delete CloudFormation stack
./scripts/delete-gateway.sh

# Note: API key providers are NOT deleted automatically
# Delete them manually via AWS Console or CLI if needed
```

## Troubleshooting

### API Key Providers Not Found

**Error**: "API key provider ARNs not found"

**Solution**: Run `./scripts/create-api-key-providers.sh` first before deploying the stack.

### OpenAPI Schema URI Not Found

**Error**: Schema URI not accessible

**Solution**: 
- Upload schemas to S3 using `./scripts/upload-schemas.sh`
- Or provide HTTP URL if schemas are publicly accessible
- Ensure S3 bucket policy allows Gateway role to read

### Cognito Authentication Fails

**Error**: JWT token validation fails

**Solution**:
- Verify the JWT token is valid and not expired (tokens are valid for 24 hours)
- Check that the token's `aud` (audience) claim matches the Gateway name
- Verify the token's `iss` (issuer) matches the Cognito User Pool
- Ensure the client ID in the token matches the configured Cognito client

### Gateway Target Not Working

**Error**: Target returns errors

**Solution**:
- For API key targets: Verify API keys are correct in providers
- For Bedrock KB target: Verify Gateway IAM role has Bedrock permissions
- Check CloudWatch logs for Gateway errors

## Integration with Other Components

- **CloudFront**: Order and Issue Management APIs are accessed via CloudFront URLs
- **Product Knowledge Base**: Uses Knowledge Base ID from `product-knowledge-base` stack
- **Shared Infrastructure**: Uses CloudFront distribution from `shared-infra/cloudfront`
