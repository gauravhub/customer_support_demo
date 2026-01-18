# Product Knowledge Base

Deploy Bedrock Knowledge Base with S3 data source and OpenSearch vector store using CloudFormation.

## Overview

This component:
- **Uploads product JSON files** to S3 at a configurable prefix
- **Creates a Bedrock Knowledge Base** resource via CloudFormation
- **Creates an S3 data source** via CloudFormation
- **Starts an ingestion job** to sync data to OpenSearch

## Architecture

```
┌─────────────────────────────────────────┐
│  Product Knowledge Base (This Folder)   │
│  - CloudFormation template              │
│  - S3 upload script                     │
│  - Ingestion job script                 │
└──────────────┬──────────────────────────┘
               │
               ▼
┌─────────────────────────────────────────┐
│  Shared Infrastructure                  │
│  (shared-infra/bedrock-kb)              │
│  - OpenSearch domain (vector store)     │
│  - S3 bucket (data storage)             │
│  - IAM roles                            │
└─────────────────────────────────────────┘
```

## Structure

```
product-knowledge-base/
├── data/                    # Source product data (JSON files)
│   ├── SRV-0001.json
│   ├── SRV-0002.json
│   └── ...
├── manifests/
│   └── product-kb.yaml      # CloudFormation template
│       - Bedrock Knowledge Base
│       - S3 Data Source
├── scripts/
│   ├── upload-data.sh              # Upload JSON files to S3
│   ├── setup-opensearch-role.sh    # Configure OpenSearch role mapping
│   ├── create-opensearch-index.sh  # Create vector index in OpenSearch
│   ├── create-kb.sh                 # Deploy CloudFormation stack
│   ├── start-ingestion.sh           # Start ingestion job
│   ├── test-retrieve.sh             # Test Bedrock Retrieve API
│   └── analyze-retrieve.sh          # Detailed retrieval analysis
├── src/
│   └── upload_to_s3.py     # S3 upload logic
├── requirements.txt         # Python dependencies
└── README.md               # This file
```

## Prerequisites

- Shared Bedrock Knowledge Bases infrastructure deployed
  - See [Bedrock Knowledge Bases](../shared-infra/README.md#bedrock-knowledge-bases) section in `shared-infra/README.md`
- AWS CLI configured with appropriate credentials
- Python 3.9+ with dependencies installed

## Deployment Steps

**Important**: Steps must be executed in order. The OpenSearch role mapping and index creation are prerequisites for the Knowledge Base creation.

### Step 1: Upload Product Data to S3

```bash
# Set S3 bucket name (from shared infrastructure outputs)
export S3_BUCKET_NAME=customer-support-kb-datasources-YOUR_ACCOUNT_ID
export S3_PREFIX=product-information/

# Upload files
./scripts/upload-data.sh
```

Or set environment variables and run Python directly:
```bash
export S3_BUCKET_NAME=<from-stack-output>
export S3_PREFIX=product-information/
python3 -m src.upload_to_s3
```

### Step 2: Setup OpenSearch Role Mapping

Before creating the Knowledge Base, you need to map the Bedrock IAM role to an OpenSearch role with necessary permissions:

```bash
./scripts/setup-opensearch-role.sh
```

This script:
- Creates an OpenSearch role (`bedrock_kb_role`) with necessary permissions
- Maps the Bedrock KB IAM role ARN to the OpenSearch role
- Required for Bedrock to access and write to OpenSearch

**Note**: This step is required because OpenSearch uses fine-grained access control (FGAC) and requires explicit role mapping.

### Step 3: Create OpenSearch Vector Index

Bedrock Knowledge Bases requires the OpenSearch index to exist before creating the KB:

```bash
./scripts/create-opensearch-index.sh
```

This script:
- Creates a vector index with FAISS engine (required for Bedrock)
- Configures the index with proper field mappings (vector, text)
- Uses dimension 1536 (for `amazon.titan-embed-text-v1`)

**Note**: The index must use FAISS engine with `innerproduct` space type for Bedrock compatibility.

### Step 4: Create Knowledge Base (CloudFormation)

```bash
# Deploy CloudFormation stack
./scripts/create-kb.sh
```

The script automatically:
- Gets values from shared infrastructure stack
- Deploys the Bedrock Knowledge Base resource
- Creates the S3 data source
- Displays stack outputs

**Environment Variables:**
- `REGION` - AWS region (default: `us-west-2`)
- `STACK_NAME` - CloudFormation stack name (default: `product-knowledge-base`)
- `S3_PREFIX` - S3 prefix (default: `product-information/`)
- `KB_NAME` - Knowledge base name (default: `product-knowledge-base`)
- `SHARED_STACK_NAME` - Shared infrastructure stack name (default: `customer-support-demo-bedrock-kb`)

### Step 5: Start Ingestion Job

```bash
# Start ingestion job
./scripts/start-ingestion.sh
```

This will start syncing the S3 data to OpenSearch.

**Note**: Ingestion jobs can take several minutes. Monitor progress using the command shown in the output.

### Step 6: Test Retrieval (Optional)

Test that the Knowledge Base is working correctly:

```bash
# Basic retrieval test
./scripts/test-retrieve.sh

# Detailed analysis with validation
./scripts/analyze-retrieve.sh
```

These scripts test various RAG queries and validate that relevant documents are being retrieved correctly.

## Configuration

The CloudFormation template (`manifests/product-kb.yaml`) accepts parameters:
- `OpenSearchDomainEndpoint` - From shared infrastructure
- `OpenSearchDomainArn` - From shared infrastructure
- `OpenSearchAdminUserSecretArn` - From shared infrastructure
- `S3BucketName` - From shared infrastructure
- `S3Prefix` - S3 prefix where data is stored (default: `product-information/`)
- `BedrockKBRoleArn` - From shared infrastructure
- `KBName` - Knowledge base name (default: `product-knowledge-base`)
- `KBDescription` - Description (default: Product specifications and information knowledge base)
- `EmbeddingModelId` - Embedding model (default: `amazon.titan-embed-text-v1`)

## Data Format

Product data is stored as JSON files in `data/` directory. Each file represents a product with:
- Product ID, SKU, brand, model
- Specifications (CPU, memory, storage, etc.)
- Use cases and tags
- Descriptions

The files are uploaded directly to S3 without transformation. Bedrock Knowledge Bases will automatically process and index them during ingestion.

## Integration with Shared Infrastructure

This component:
1. **Uses** the shared S3 bucket (from infrastructure)
2. **Uses** the shared OpenSearch domain (from infrastructure)
3. **Uses** the shared IAM role (from infrastructure)
4. **Configures** OpenSearch role mapping (for FGAC permissions)
5. **Creates** the OpenSearch vector index (required by Bedrock)
6. **Creates** the Bedrock Knowledge Base resource (via CloudFormation)
7. **Creates** the S3 data source (via CloudFormation)
8. **Manages** ingestion jobs (via script)

The actual OpenSearch domain, S3 bucket, and IAM roles are managed in `shared-infra/bedrock-kb/`.

## Troubleshooting

### Ingestion Job Fails with Metadata Mapping Error

If you see errors like "object mapping for [metadata] tried to parse field [metadata] as object, but found a concrete value":

- **Solution**: The OpenSearch index should NOT have an explicit `metadata` field mapping. The `create-opensearch-index.sh` script creates the index without this mapping to allow dynamic metadata handling.

### Knowledge Base Creation Fails with Permission Errors

If you see OpenSearch permission errors:

- **Solution**: Ensure Step 2 (Setup OpenSearch Role Mapping) was executed successfully. The IAM role must be mapped to an OpenSearch role with `indices_all` permissions.

### Knowledge Base Creation Fails with "Index Not Found"

If you see errors about the index not existing:

- **Solution**: Ensure Step 3 (Create OpenSearch Vector Index) was executed successfully. The index must exist before creating the Knowledge Base.

### Index Creation Fails with Engine Type Error

If you see errors about invalid engine type:

- **Solution**: The index must use FAISS engine (not nmslib) with `innerproduct` space type. The `create-opensearch-index.sh` script uses the correct configuration.

## Cleanup

```bash
# Delete CloudFormation stack
aws cloudformation delete-stack \
  --stack-name product-knowledge-base \
  --region us-west-2

# Note: This does NOT delete the S3 data. Delete manually if needed:
# aws s3 rm s3://<bucket-name>/product-information/ --recursive
```
