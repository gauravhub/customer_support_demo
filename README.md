# Customer Support Demo

An AI-powered customer support system with REST APIs, Knowledge Base, and MCP Gateway deployed on AWS:
- **Order Management API** - Query order management database
- **Issue Management API** - Manage JIRA issues
- **Product Knowledge Base** - Bedrock Knowledge Base with product information
- **MCP Gateway** - Model Context Protocol gateway exposing all services to AI agents

## Architecture

- **Shared EKS Cluster**: `customer-support-demo` hosts both APIs
- **Shared CloudFront Distribution**: HTTPS endpoints with path-based routing
- **Shared S3 Bucket**: Data sources for Knowledge Base and MCP schemas
- **Bedrock Knowledge Base**: Product information with OpenSearch vector store
- **MCP Gateway**: Unified interface for AI agents (Cognito-secured)
- **Path-Based Routing**:
  - `/order-management/*` → Order Management API
  - `/issue-management/*` → Issue Management API

## Quick Start

### Prerequisites

- AWS CLI configured with appropriate credentials
- eksctl 0.221.0+ installed
- kubectl installed
- Docker installed
- Python 3.9+ (for scripts and APIs)

### Deployment Order

**⚠️ IMPORTANT**: Components must be deployed in this specific order due to dependencies:

#### Phase 1: Shared Infrastructure
1. **Bedrock Knowledge Bases Infrastructure** (`shared-infra/bedrock-kb/`)
   - Creates S3 bucket for data sources
   - Creates OpenSearch domain
   - See `shared-infra/README.md` → [Bedrock Knowledge Bases](#bedrock-knowledge-bases)

2. **EKS Cluster** (`shared-infra/eks-cluster/`)
   - Creates Kubernetes cluster
   - See `shared-infra/README.md` → [EKS Cluster](#eks-cluster)

3. **CloudFront Distribution** (`shared-infra/cloudfront/`)
   - Creates HTTPS endpoints
   - See `shared-infra/README.md` → [CloudFront Distribution](#cloudfront-distribution)

#### Phase 2: Application Services
4. **Order Management API** (`order-management-api/`)
   - Build, push Docker image, deploy to EKS
   - See `order-management-api/README.md`

5. **Issue Management API** (`issue-management-api/`)
   - Build, push Docker image, deploy to EKS
   - See `issue-management-api/README.md`

#### Phase 3: AI/ML Services
6. **Product Knowledge Base** (`product-knowledge-base/`)
   - Upload product data to S3
   - Create Bedrock Knowledge Base
   - Start ingestion job
   - See `product-knowledge-base/README.md`

7. **MCP Gateway** (`mcp-gateway/`)
   - Create API key providers
   - Upload OpenAPI schemas to S3
   - Deploy gateway with Cognito auth
   - See `mcp-gateway/README.md`

### Quick Access

```bash
# Get CloudFront URL
aws cloudformation describe-stacks \
  --stack-name customer-support-demo-cloudfront \
  --query 'Stacks[0].Outputs[?OutputKey==`CloudFrontURL`].OutputValue' \
  --output text

# Get MCP Gateway URL
aws cloudformation describe-stacks \
  --stack-name customer-support-demo-mcp-gateway \
  --query 'Stacks[0].Outputs[?OutputKey==`GatewayUrl`].OutputValue' \
  --output text
```

**Endpoints:**
- Order Management API: `https://<cloudfront-domain>/order-management/*`
- Issue Management API: `https://<cloudfront-domain>/issue-management/*`
- MCP Gateway: `https://<gateway-id>.gateway.bedrock-agentcore.us-west-2.amazonaws.com/mcp`

## Project Structure

```
customer-support-demo/
├── shared-infra/                    # Phase 1: Shared infrastructure (deploy first)
│   ├── README.md
│   ├── bedrock-kb/                  # S3 bucket + OpenSearch (deploy 1st)
│   ├── eks-cluster/                 # Kubernetes cluster (deploy 2nd)
│   └── cloudfront/                  # HTTPS distribution (deploy 3rd)
│
├── order-management-api/            # Phase 2: Application services
│   ├── README.md
│   ├── manifest/                    # K8s deployment manifests
│   ├── src/                         # FastAPI application
│   └── data/                        # Sample data + OpenAPI spec
│
├── issue-management-api/            # Phase 2: Application services
│   ├── README.md
│   ├── manifest/                    # K8s deployment manifests
│   ├── src/                         # FastAPI application
│   └── data/                        # Sample data + OpenAPI spec
│
├── product-knowledge-base/          # Phase 3: AI/ML services
│   ├── README.md
│   ├── data/                        # Product JSON files
│   ├── manifests/                   # CloudFormation templates
│   ├── scripts/                     # Deployment scripts
│   └── src/                         # Upload utilities
│
└── mcp-gateway/                     # Phase 3: AI/ML services (deploy last)
    ├── README.md
    ├── manifests/                   # CloudFormation template
    ├── scripts/                     # Deployment + test scripts
    └── schemas/                     # API schemas (generated)
```

## Documentation

### Shared Infrastructure
- **Overview**: `shared-infra/README.md`
- **Bedrock KB**: `shared-infra/bedrock-kb/README.md` - S3 bucket and OpenSearch setup
- **EKS Cluster**: See [EKS Cluster section](shared-infra/README.md#eks-cluster)
- **CloudFront**: See [CloudFront section](shared-infra/README.md#cloudfront-distribution)

### Application Services
- **Order Management API**: `order-management-api/README.md` - Order data REST API
- **Issue Management API**: `issue-management-api/README.md` - JIRA integration REST API

### AI/ML Services
- **Product Knowledge Base**: `product-knowledge-base/README.md` - Bedrock KB deployment
- **MCP Gateway**: `mcp-gateway/README.md` - AI agent gateway with all services

## Component Dependencies

```
bedrock-kb (S3 + OpenSearch)
    ↓
    ├─→ product-knowledge-base (uses S3 bucket)
    └─→ mcp-gateway (uses S3 bucket for schemas)

eks-cluster
    ↓
    ├─→ order-management-api (deployed to EKS)
    └─→ issue-management-api (deployed to EKS)

cloudfront (depends on APIs)
    ↓
    └─→ mcp-gateway (uses CloudFront URLs in OpenAPI specs)

mcp-gateway (depends on everything)
    ├─→ order-management-api (OpenAPI target)
    ├─→ issue-management-api (OpenAPI target)
    └─→ product-knowledge-base (Smithy target)
```
