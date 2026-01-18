# Bedrock Knowledge Bases Infrastructure

Shared AWS Bedrock Knowledge Bases infrastructure with OpenSearch backend.

## Overview

This infrastructure component provides:
- **Bedrock Knowledge Bases**: Shared service that can host multiple knowledge bases
- **OpenSearch Domain**: Vector store backend for knowledge bases
- **IAM Roles & Policies**: Permissions for Bedrock to access OpenSearch and S3
- **S3 Bucket**: Shared storage for knowledge base data sources

## Architecture

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

## Structure

```
bedrock-kb/
├── manifests/
│   └── bedrock-kb.yaml          # CloudFormation template
│       - OpenSearch domain
│       - Bedrock KB service configuration
│       - IAM roles & policies
│       - S3 bucket for data sources
└── scripts/
    ├── create-kb-infra.sh       # Deploy infrastructure
    └── delete-kb-infra.sh       # Delete infrastructure
```

## Deployment

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

**Note**: Infrastructure deployment takes 10-20 minutes (OpenSearch domain creation is the longest step).

### Delete Infrastructure

```bash
cd bedrock-kb
./scripts/delete-kb-infra.sh
```

**Warning**: This deletes the OpenSearch domain, Bedrock KB configuration, and S3 bucket.

## Outputs

After deployment, the stack outputs:
- `OpenSearchDomainEndpoint` - OpenSearch domain endpoint
- `OpenSearchDomainArn` - OpenSearch domain ARN
- `S3BucketName` - S3 bucket name for data sources
- `BedrockKBRoleArn` - IAM role ARN for Bedrock KB service
- `OpenSearchAdminUserSecretArn` - Secrets Manager ARN for OpenSearch admin user

## Usage by Applications

Applications (like `product-knowledge-base/`) can:
1. Use the shared OpenSearch domain endpoint
2. Upload data sources to the shared S3 bucket
3. Create knowledge bases via Bedrock API using the configured infrastructure
4. Reference the IAM role for Bedrock KB service access

See `../../product-knowledge-base/README.md` for product-specific ingestion logic.
