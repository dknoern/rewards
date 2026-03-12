#!/bin/bash

# Rewards Program Backend Destroy Script
# Usage: ./scripts/destroy.sh [environment]
# Example: ./scripts/destroy.sh dev

set -e

# Default values
ENVIRONMENT=${1:-dev}

# Validate environment
case $ENVIRONMENT in
  dev|staging|prod)
    echo "🗑️  Destroying $ENVIRONMENT environment"
    ;;
  *)
    echo "❌ Invalid environment: $ENVIRONMENT"
    echo "Valid environments: dev, staging, prod"
    exit 1
    ;;
esac

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Extra confirmation for production
if [ "$ENVIRONMENT" = "prod" ]; then
    echo -e "${RED}🚨 WARNING: You are about to destroy the PRODUCTION environment!${NC}"
    echo -e "${RED}This action is IRREVERSIBLE and will delete all production data!${NC}"
    echo ""
    read -p "Type 'DELETE PRODUCTION' to confirm: " -r
    if [[ ! $REPLY == "DELETE PRODUCTION" ]]; then
        echo "❌ Production destruction cancelled"
        exit 1
    fi
fi

# Confirmation for other environments
echo -e "${YELLOW}⚠️  WARNING: This will destroy all resources in the $ENVIRONMENT environment${NC}"
echo "This includes:"
echo "  - DynamoDB table and all data"
echo "  - Lambda functions"
echo "  - API Gateway"
echo "  - CloudWatch logs and dashboards"
echo "  - EventBridge rules"
echo "  - All monitoring and alarms"
echo ""

read -p "Are you sure you want to continue? (yes/no): " -r
if [[ ! $REPLY =~ ^yes$ ]]; then
    echo "❌ Destruction cancelled"
    exit 1
fi

# Set environment variable
export ENVIRONMENT=$ENVIRONMENT

echo -e "${YELLOW}🗑️  Destroying stack...${NC}"

# Destroy the stack
cdk destroy --context environment=$ENVIRONMENT --force

echo -e "${GREEN}✅ Environment $ENVIRONMENT has been destroyed${NC}"

# Environment-specific cleanup notes
case $ENVIRONMENT in
  prod)
    echo -e "${RED}📋 PRODUCTION CLEANUP COMPLETED${NC}"
    echo "- Verify all resources have been deleted"
    echo "- Check for any remaining costs"
    echo "- Update documentation"
    ;;
  staging)
    echo -e "${YELLOW}📋 STAGING CLEANUP COMPLETED${NC}"
    echo "- Environment ready for next deployment"
    ;;
  dev)
    echo -e "${GREEN}📋 DEVELOPMENT CLEANUP COMPLETED${NC}"
    echo "- Environment ready for next deployment"
    ;;
esac