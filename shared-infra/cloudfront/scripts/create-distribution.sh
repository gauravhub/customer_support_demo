#!/bin/bash

# Script to create CloudFront distribution for customer-support-demo APIs
# This provides HTTPS endpoint using CloudFront's default *.cloudfront.net certificate
# Supports both order-management-api and issue-management-api

set -e

# Configuration - can be overridden via environment variables
REGION="${REGION:-us-west-2}"
STACK_NAME="${STACK_NAME:-customer-support-demo-cloudfront}"
NAMESPACE="${NAMESPACE:-default}"
ORDER_INGRESS_NAME="${ORDER_INGRESS_NAME:-order-management-api-ingress}"
ISSUE_INGRESS_NAME="${ISSUE_INGRESS_NAME:-issue-management-api-ingress}"

echo "=========================================="
echo "CREATING CLOUDFRONT DISTRIBUTION"
echo "=========================================="
echo "Stack Name: $STACK_NAME"
echo "Region: $REGION"
echo ""

# Check if kubectl is available
if ! command -v kubectl &> /dev/null; then
    echo "Error: kubectl not found. Please install kubectl first."
    exit 1
fi

# Check if AWS CLI is available
if ! command -v aws &> /dev/null; then
    echo "Error: AWS CLI not found. Please install AWS CLI first."
    exit 1
fi

# Get ALB hostnames from Kubernetes ingresses
echo "Getting ALB hostnames from Kubernetes ingresses..."

ORDER_ALB_HOSTNAME=""
ISSUE_ALB_HOSTNAME=""

# Try to get order-management-api ALB hostname
if kubectl get ingress "$ORDER_INGRESS_NAME" -n "$NAMESPACE" &>/dev/null; then
    ORDER_ALB_HOSTNAME=$(kubectl get ingress "$ORDER_INGRESS_NAME" -n "$NAMESPACE" \
        -o jsonpath='{.status.loadBalancer.ingress[0].hostname}' 2>/dev/null || echo "")
    if [ -n "$ORDER_ALB_HOSTNAME" ]; then
        echo "✓ Order Management API ALB: $ORDER_ALB_HOSTNAME"
    else
        echo "⚠ Order Management API ingress exists but ALB hostname not available yet"
    fi
else
    echo "⚠ Order Management API ingress not found: $ORDER_INGRESS_NAME"
fi

# Try to get issue-management-api ALB hostname
if kubectl get ingress "$ISSUE_INGRESS_NAME" -n "$NAMESPACE" &>/dev/null; then
    ISSUE_ALB_HOSTNAME=$(kubectl get ingress "$ISSUE_INGRESS_NAME" -n "$NAMESPACE" \
        -o jsonpath='{.status.loadBalancer.ingress[0].hostname}' 2>/dev/null || echo "")
    if [ -n "$ISSUE_ALB_HOSTNAME" ]; then
        echo "✓ Issue Management API ALB: $ISSUE_ALB_HOSTNAME"
    else
        echo "⚠ Issue Management API ingress exists but ALB hostname not available yet"
    fi
else
    echo "⚠ Issue Management API ingress not found: $ISSUE_INGRESS_NAME"
fi

echo ""

# Check if both ALBs are available
if [ -z "$ORDER_ALB_HOSTNAME" ] || [ -z "$ISSUE_ALB_HOSTNAME" ]; then
    echo "Error: Both ALB hostnames are required. Please deploy both APIs first."
    echo ""
    echo "To deploy APIs:"
    echo "  cd ../../order-management-api/manifest && kubectl apply -f ."
    echo "  cd ../../issue-management-api/manifest && kubectl apply -f ."
    exit 1
fi

# Check if stack already exists
if aws cloudformation describe-stacks --stack-name "$STACK_NAME" --region "$REGION" &>/dev/null; then
    echo "CloudFormation stack '$STACK_NAME' already exists."
    read -p "Do you want to update it? (y/n) " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        echo "Updating CloudFormation stack..."
        
        # Build parameters
        PARAMS="ParameterKey=OrderManagementALBDnsName,ParameterValue=$ORDER_ALB_HOSTNAME"
        PARAMS="$PARAMS ParameterKey=IssueManagementALBDnsName,ParameterValue=$ISSUE_ALB_HOSTNAME"
        
        aws cloudformation update-stack \
            --stack-name "$STACK_NAME" \
            --template-body file://manifests/cloudfront.yaml \
            --parameters $PARAMS \
            --region "$REGION" \
            --capabilities CAPABILITY_IAM
        
        echo "Waiting for stack update to complete..."
        aws cloudformation wait stack-update-complete \
            --stack-name "$STACK_NAME" \
            --region "$REGION"
    else
        echo "Skipping update. Using existing stack."
    fi
else
    echo "Creating CloudFormation stack..."
    
    # Build parameters
    PARAMS="ParameterKey=OrderManagementALBDnsName,ParameterValue=$ORDER_ALB_HOSTNAME"
    PARAMS="$PARAMS ParameterKey=IssueManagementALBDnsName,ParameterValue=$ISSUE_ALB_HOSTNAME"
    
    aws cloudformation create-stack \
        --stack-name "$STACK_NAME" \
        --template-body file://manifests/cloudfront.yaml \
        --parameters $PARAMS \
        --region "$REGION" \
        --capabilities CAPABILITY_IAM
    
    echo "Waiting for stack creation to complete (this may take 10-15 minutes)..."
    aws cloudformation wait stack-create-complete \
        --stack-name "$STACK_NAME" \
        --region "$REGION"
fi

# Get CloudFront domain name
echo ""
echo "Getting CloudFront distribution details..."
CLOUDFRONT_DOMAIN=$(aws cloudformation describe-stacks \
    --stack-name "$STACK_NAME" \
    --region "$REGION" \
    --query 'Stacks[0].Outputs[?OutputKey==`CloudFrontDomainName`].OutputValue' \
    --output text)

CLOUDFRONT_URL=$(aws cloudformation describe-stacks \
    --stack-name "$STACK_NAME" \
    --region "$REGION" \
    --query 'Stacks[0].Outputs[?OutputKey==`CloudFrontURL`].OutputValue' \
    --output text)

if [ -z "$CLOUDFRONT_DOMAIN" ]; then
    echo "Warning: Could not get CloudFront domain name from stack outputs."
    echo "The stack may still be deploying. Check AWS Console for status."
    exit 1
fi

echo ""
echo "=========================================="
echo "CLOUDFRONT SETUP COMPLETE"
echo "=========================================="
echo "CloudFront Domain: $CLOUDFRONT_DOMAIN"
echo "CloudFront URL: $CLOUDFRONT_URL"
echo ""
echo "Your APIs are now available at:"
echo "  Order Management API:"
echo "    - Direct ALB: http://$ORDER_ALB_HOSTNAME"
echo "    - Via CloudFront: $CLOUDFRONT_URL/order-management/*"
echo "  Issue Management API:"
echo "    - Direct ALB: http://$ISSUE_ALB_HOSTNAME"
echo "    - Via CloudFront: $CLOUDFRONT_URL/issue-management/*"
echo ""
echo "Next steps:"
echo "1. Wait for CloudFront distribution to fully deploy (5-15 minutes)"
echo "2. Test the endpoints:"
echo "   curl $CLOUDFRONT_URL/order-management/"
echo "   curl $CLOUDFRONT_URL/issue-management/"
echo ""
echo "To check deployment status:"
echo "  aws cloudformation describe-stacks --stack-name $STACK_NAME --region $REGION"
echo ""
echo "To delete the CloudFront distribution:"
echo "  aws cloudformation delete-stack --stack-name $STACK_NAME --region $REGION"
echo ""
