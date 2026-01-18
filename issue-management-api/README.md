# Issue Management API

FastAPI REST API wrapper for managing JIRA issues with automatic Swagger documentation.

## Features

- REST endpoints for JIRA issue operations (get, update, attachments)
- API key authentication
- Self-contained Docker image
- Swagger/OpenAPI docs at `/docs`

## Authentication

All endpoints (except `/`, `/docs`, `/redoc`) require `X-API-Key` header with base64-encoded key.

**Example:**
```bash
curl -H "X-API-Key: cHJvZC1rZXktNjc4OTA=" http://localhost:8000/api/issue/AS-1
```

**API Key** (in `data/api_keys.json`):
- `cHJvZC1rZXktNjc4OTA=`

⚠️ **Change default keys before production!**

## JIRA Configuration

JIRA credentials are configured via a `.env` file that is baked into the Docker image.

**Required variables** (in `.env` file):
- `JIRA_API_USERNAME` - JIRA email
- `JIRA_API_TOKEN` - API token ([create here](https://id.atlassian.com/manage-profile/security/api-tokens))
- `JIRA_INSTANCE_URL` - Instance URL (e.g., `https://your-domain.atlassian.net`)

**Optional variables**:
- `JIRA_PROJECT_KEY` - Default project key
- `JIRA_ASSIGNEE_USERNAME` - Default assignee
- `JIRA_CATEGORY_FIELD_ID` - Category field ID (without 'customfield_' prefix)
- `JIRA_RESPONSE_FIELD_ID` - Response field ID (without 'customfield_' prefix)

See `env.example` for all options. Create `.env` from `env.example` before building the Docker image.

## API Endpoints

### Issue Operations
- `GET /api/issue/{issue_key}` - Get issue details
- `GET /api/issue/{issue_key}/field?field_name=...` - Get field value
- `GET /api/issue/{issue_key}/attachments` - Get list of attachments
- `PUT /api/issue/{issue_key}/field` - Update field
  - Request body: `{"field_name": "...", "value": "..."}`
  - To assign an issue, use `field_name: "assignee"` with the assignee email/username as `value`

**Examples:**
```bash
# Get issue
curl -H "X-API-Key: cHJvZC1rZXktNjc4OTA=" http://localhost:8000/api/issue/AS-1

# Get field value
curl -H "X-API-Key: cHJvZC1rZXktNjc4OTA=" "http://localhost:8000/api/issue/AS-1/field?field_name=summary"

# Get attachments
curl -H "X-API-Key: cHJvZC1rZXktNjc4OTA=" http://localhost:8000/api/issue/AS-1/attachments

# Update field
curl -X PUT -H "X-API-Key: cHJvZC1rZXktNjc4OTA=" \
  -H "Content-Type: application/json" \
  -d '{"field_name": "customfield_10071", "value": "Category Value"}' \
  http://localhost:8000/api/issue/AS-1/field

# Assign issue (using field update endpoint)
curl -X PUT -H "X-API-Key: cHJvZC1rZXktNjc4OTA=" \
  -H "Content-Type: application/json" \
  -d '{"field_name": "assignee", "value": "user@example.com"}' \
  http://localhost:8000/api/issue/AS-1/field
```

**Attachment Response Format:**
```json
{
  "attachments": [
    {
      "id": "10036",
      "filename": "transaction_failed.png",
      "size": 505170,
      "mimeType": "image/png",
      "content": "https://your-domain.atlassian.net/rest/api/2/attachment/content/10036",
      "thumbnail": "https://your-domain.atlassian.net/rest/api/2/attachment/thumbnail/10036",
      "created": "2026-01-05T13:53:34.461-0600",
      "author": "user@example.com"
    }
  ],
  "count": 1
}
```

### Documentation
- `GET /docs` - Swagger UI
- `GET /redoc` - ReDoc

## Quick Start

### Local Development

```bash
# Install dependencies
uv pip install -e .

# Set environment variables (or use .env file)
export JIRA_API_USERNAME=your-email@example.com
export JIRA_API_TOKEN=your-api-token
export JIRA_INSTANCE_URL=https://your-domain.atlassian.net

# Run
uvicorn src.api.main:app --reload --host 0.0.0.0 --port 8000
```

### Docker

```bash
# Create .env file first
cp env.example .env
# Edit .env with your JIRA credentials

# Build (includes .env file in image)
docker build -t issue-management-api .

# Run
docker run -d -p 8000:8000 --name issue-management-api issue-management-api
```

The `.env` file is loaded automatically from the Docker image.

## EKS Deployment

This API uses the shared `customer-support-demo-cluster`. See `../shared-infra/README.md` for cluster setup.

### Prerequisites
- Shared EKS cluster created (`../shared-infra/eks-cluster/scripts/create-cluster.sh`)
- kubectl configured
- Docker and AWS CLI installed

### Steps

1. **Create .env file:**
```bash
# Create .env file from env.example and fill in your JIRA credentials
cp env.example .env
# Edit .env with your values (at minimum: JIRA_API_USERNAME, JIRA_API_TOKEN, JIRA_INSTANCE_URL)
```

2. **Build and push to ECR:**
```bash
export REGION="us-west-2"
export ACCOUNT_ID="123456789012"
docker build -t issue-management-api .
aws ecr create-repository --repository-name issue-management-api --region $REGION || true
aws ecr get-login-password --region $REGION | \
  docker login --username AWS --password-stdin $ACCOUNT_ID.dkr.ecr.$REGION.amazonaws.com
docker tag issue-management-api:latest $ACCOUNT_ID.dkr.ecr.$REGION.amazonaws.com/issue-management-api:latest
docker push $ACCOUNT_ID.dkr.ecr.$REGION.amazonaws.com/issue-management-api:latest
```

3. **Deploy:**
```bash
# Option 1: Using the deployment script (recommended)
export ACCOUNT_ID="123456789012"
export REGION="us-west-2"
./scripts/deploy.sh

# Option 2: Pass values as arguments
./scripts/deploy.sh 123456789012 us-west-2

# Option 3: Manual deployment (if you prefer)
# First, replace ACCOUNT_ID and REGION in manifest/deployment.yaml manually
cd manifest
kubectl apply -f deployment.yaml
kubectl apply -f service.yaml
kubectl apply -f ingress.yaml
```

4. **Get endpoint:**
```bash
kubectl get ingress issue-management-api-ingress \
  -o jsonpath='{.status.loadBalancer.ingress[0].hostname}'
```

### Monitoring

```bash
kubectl logs -f deployment/issue-management-api
kubectl get pods -l app=issue-management-api
kubectl describe deployment issue-management-api
```

### Cleanup

```bash
kubectl delete -f manifest/ingress.yaml
kubectl delete -f manifest/service.yaml
kubectl delete -f manifest/deployment.yaml
```

## Project Structure

```
issue-management-api/
├── src/
│   ├── config.py           # Configuration (loads .env file)
│   ├── api/main.py         # FastAPI app
│   └── services/jira.py    # JIRA service wrapper
├── manifest/               # K8s manifests
│   ├── deployment.yaml     # Deployment (with ACCOUNT_ID and REGION placeholders)
│   ├── service.yaml
│   └── ingress.yaml
├── scripts/                # Deployment scripts
│   └── deploy.sh          # Automated deployment script
├── data/
│   └── api_keys.json       # API keys
├── env.example             # Environment variables template
└── Dockerfile              # Copies .env into image
```

## Notes

- Docker image is self-contained (no volume mounts)
- JIRA credentials are loaded from `.env` file in the Docker image
- Uses shared EKS cluster infrastructure (see `../shared-infra/`)
- ⚠️ **Security Note**: The `.env` file is baked into the Docker image. For production, consider using Kubernetes secrets or external secret managers.
