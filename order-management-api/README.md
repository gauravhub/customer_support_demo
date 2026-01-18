# Order Management API

FastAPI REST API for querying order management database with automatic Swagger documentation.

## Features

- REST endpoints for querying customers, orders, transactions, and refunds
- API key authentication
- Automatic database initialization from JSON files
- Self-contained Docker image
- Swagger/OpenAPI docs at `/docs`

## Authentication

All endpoints (except `/`, `/docs`, `/redoc`) require `X-API-Key` header with base64-encoded key.

**Example:**
```bash
curl -H "X-API-Key: ZGV2LWtleS0xMjM0NQ==" http://localhost:8000/api/customer?email=test@example.com
```

**API Key** (in `data/api_keys.json`):
- `ZGV2LWtleS0xMjM0NQ==`

⚠️ **Change default keys before production!**

## API Endpoints

### Customer
- `GET /api/customer?email=...` - Find customer by email
- `GET /api/customer?customer_id=...` - Find customer by ID
- `GET /api/customer?email=...&customer_id=...` - Find by email or ID

### Order
- `GET /api/order?order_no=...` - Find order by order number

### Transaction
- `GET /api/transaction?transaction_id=...` - Find transaction by ID
- `GET /api/transaction/order/{order_no}` - Get transaction for order

### Refund
- `GET /api/refund/order/{order_no}` - Get refund for order

### Documentation
- `GET /docs` - Swagger UI
- `GET /redoc` - ReDoc

## Quick Start

### Local Development

```bash
# Install dependencies
uv pip install -e .

# Run
uvicorn src.api.main:app --reload --host 0.0.0.0 --port 8000
```

### Docker

```bash
# Build
docker build -t order-management-api .

# Run
docker run -d -p 8000:8000 --name order-management-api order-management-api
```

## EKS Deployment

This API uses the shared `customer-support-demo` EKS cluster. See `../shared-infra/README.md` for cluster setup.

### Prerequisites
- Shared EKS cluster created (`../shared-infra/eks-cluster/scripts/create-cluster.sh`)
- kubectl configured
- Docker and AWS CLI installed

### Steps

1. **Build and push to ECR:**
```bash
export REGION="us-west-2"
export ACCOUNT_ID="123456789012"
docker build -t order-management-api .
aws ecr create-repository --repository-name order-management-api --region $REGION
aws ecr get-login-password --region $REGION | \
  docker login --username AWS --password-stdin $ACCOUNT_ID.dkr.ecr.$REGION.amazonaws.com
docker tag order-management-api:latest $ACCOUNT_ID.dkr.ecr.$REGION.amazonaws.com/order-management-api:latest
docker push $ACCOUNT_ID.dkr.ecr.$REGION.amazonaws.com/order-management-api:latest
```

2. **Deploy:**
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

3. **Get endpoint:**
```bash
kubectl get ingress order-management-api-ingress \
  -o jsonpath='{.status.loadBalancer.ingress[0].hostname}'
```

### Monitoring

```bash
kubectl logs -f deployment/order-management-api
kubectl get pods -l app=order-management-api
kubectl describe deployment order-management-api
```

### Cleanup

```bash
kubectl delete -f manifest/ingress.yaml
kubectl delete -f manifest/service.yaml
kubectl delete -f manifest/deployment.yaml
```

## Project Structure

```
order-management-api/
├── src/
│   ├── config.py           # Configuration
│   ├── api/main.py         # FastAPI app
│   └── services/database.py # Database service
├── manifest/               # K8s manifests
│   ├── deployment.yaml     # Deployment (with ACCOUNT_ID and REGION placeholders)
│   ├── service.yaml
│   └── ingress.yaml
├── scripts/                # Deployment scripts
│   └── deploy.sh          # Automated deployment script
├── data/                   # JSON data files
│   ├── customers.json
│   ├── orders.json
│   ├── transactions.json
│   ├── refunds.json
│   └── api_keys.json
└── Dockerfile
```

## Notes

- Docker image is self-contained (no volume mounts)
- Database auto-initializes from JSON files on startup
- SQLite database is ephemeral (resets on pod restart)
- Uses shared EKS cluster infrastructure (see `../shared-infra/`)
