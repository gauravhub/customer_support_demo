# AWS Infrastructure

Shared AWS infrastructure deployment for customer-support-demo project.

## Overview

- **EKS Cluster**: Shared Kubernetes cluster (`customer-support-demo`)
- **CloudFront Distribution**: Shared HTTPS endpoint with path-based routing
- **Bedrock Knowledge Bases**: Shared infrastructure for knowledge bases with OpenSearch backend

## Structure

```
shared-infra/
├── eks-cluster/
│   ├── manifests/
│   │   ├── cluster.yaml              # EKS cluster configuration
│   │   ├── ingressclass.yaml         # IngressClass for ALB
│   │   └── ingressclassparams.yaml   # IngressClassParams
│   └── scripts/
│       ├── create-cluster.sh         # Create EKS cluster
│       └── delete-cluster.sh         # Delete EKS cluster
└── cloudfront/
    ├── manifests/
    │   └── cloudfront.yaml           # CloudFront distribution (CloudFormation)
    └── scripts/
        ├── create-distribution.sh    # Create CloudFront distribution
        └── delete-distribution.sh    # Delete CloudFront distribution
└── bedrock-kb/
    ├── manifests/
    │   └── bedrock-kb.yaml           # Bedrock KB infrastructure (CloudFormation)
    └── scripts/
        ├── create-kb-infra.sh        # Create Bedrock KB infrastructure
        └── delete-kb-infra.sh       # Delete Bedrock KB infrastructure
```

## EKS Cluster

### Create Cluster

```bash
cd eks-cluster
./scripts/create-cluster.sh
```

Or with custom region:
```bash
REGION=us-west-2 ./scripts/create-cluster.sh
```

**Environment Variables:**
- `REGION` - AWS region (default: `us-west-2`)
- `CLUSTER_NAME` - Cluster name (default: `customer-support-demo`)
- `CLUSTER_VERSION` - Kubernetes version (default: `1.34`)

**Configuration:**
Edit `eks-cluster/manifests/cluster.yaml` to customize:
- Region
- Kubernetes version
- VPC CIDR
- CloudWatch logging
- Tags

**Note**: Cluster creation takes 15-20 minutes.

### Delete Cluster

```bash
cd eks-cluster
./scripts/delete-cluster.sh
```

**Warning**: This deletes the entire cluster and all resources, including deployed APIs.

## CloudFront Distribution

### Create Distribution

```bash
cd cloudfront
./scripts/create-distribution.sh
```

Automatically detects ALB hostnames from Kubernetes ingresses and creates distribution with path-based routing.

**Environment Variables:**
- `REGION` - AWS region (default: `us-west-2`)
- `STACK_NAME` - CloudFormation stack name (default: `customer-support-demo-cloudfront`)
- `NAMESPACE` - Kubernetes namespace (default: `default`)
- `ORDER_INGRESS_NAME` - Order API ingress name (default: `order-management-api-ingress`)
- `ISSUE_INGRESS_NAME` - Issue API ingress name (default: `issue-management-api-ingress`)

**Configuration:**
Edit `cloudfront/manifests/cloudfront.yaml` to customize:
- Cache behaviors
- Price class
- Error responses
- Origin configurations

**Note**: CloudFront distribution deployment takes 5-15 minutes.

### Path-Based Routing

- `/order-management/*` → Order Management API ALB
- `/issue-management/*` → Issue Management API ALB
- `/` → Defaults to Order Management API

### Update Distribution

```bash
cd cloudfront
./scripts/create-distribution.sh
```

Script detects existing stack and prompts to update.

### Delete Distribution

```bash
cd cloudfront
./scripts/delete-distribution.sh
```

## Bedrock Knowledge Bases

Shared infrastructure for Bedrock Knowledge Bases with OpenSearch backend. This infrastructure can support multiple knowledge bases (Product KB, Support KB, etc.).

### Overview

This infrastructure component provides:
- **Bedrock Knowledge Bases**: Shared service that can host multiple knowledge bases
- **OpenSearch Domain**: Vector store backend for knowledge bases
- **IAM Roles & Policies**: Permissions for Bedrock to access OpenSearch and S3
- **S3 Bucket**: Shared storage for knowledge base data sources

### Architecture

```
┌─────────────────────────────────────────┐
│  Bedrock Knowledge Bases (Shared)      │
│  - Can host multiple KBs                │
│  - Product KB, Support KB, etc.         │
└──────────────┬──────────────────────────┘
               │
               ▼
┌─────────────────────────────────────────┐
│  OpenSearch Domain (Shared)             │
│  - Vector embeddings storage            │
│  - Indexed by knowledge base            │
└─────────────────────────────────────────┘
               │
               ▼
┌─────────────────────────────────────────┐
│  S3 Bucket (Shared)                     │
│  - Data source storage                  │
│  - Organized by KB/datasource            │
└─────────────────────────────────────────┘
```

### Prerequisites

- AWS CLI configured
- Appropriate IAM permissions for:
  - Bedrock
  - OpenSearch
  - S3
  - IAM role creation

### Create Infrastructure

```bash
cd bedrock-kb
./scripts/create-kb-infra.sh
```

**Environment Variables:**
- `REGION` - AWS region (default: `us-west-2`)
- `STACK_NAME` - CloudFormation stack name (default: `customer-support-demo-bedrock-kb`)
- `OPENSEARCH_DOMAIN_NAME` - OpenSearch domain name (default: `customer-support-kb-opensearch`)
- `S3_BUCKET_NAME` - S3 bucket for data sources (default: `customer-support-kb-datasources-<account-id>`)

**Configuration:**
Edit `bedrock-kb/manifests/bedrock-kb.yaml` to customize:
- OpenSearch instance type and size
- S3 bucket configuration
- IAM roles and policies

**Note**: Infrastructure deployment takes 10-20 minutes (OpenSearch domain creation is the longest step).

### Delete Infrastructure

```bash
cd bedrock-kb
./scripts/delete-kb-infra.sh
```

**Warning**: This deletes the OpenSearch domain, Bedrock KB configuration, and S3 bucket.

### Outputs

After deployment, the stack outputs:
- `OpenSearchDomainEndpoint` - OpenSearch domain endpoint
- `OpenSearchDomainArn` - OpenSearch domain ARN
- `S3BucketName` - S3 bucket name for data sources
- `BedrockKBRoleArn` - IAM role ARN for Bedrock KB service
- `OpenSearchAdminUserSecretArn` - Secrets Manager ARN for OpenSearch admin user

**Important**: Save the OpenSearch admin user password displayed after deployment. It's also stored in Secrets Manager.

### Usage by Applications

Applications (like `product-knowledge-base/`) can:
1. Use the shared OpenSearch domain endpoint
2. Upload data sources to the shared S3 bucket
3. Create knowledge bases via Bedrock API using the configured infrastructure
4. Reference the IAM role for Bedrock KB service access

See `../product-knowledge-base/README.md` for product-specific ingestion logic.
