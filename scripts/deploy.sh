#!/bin/bash

# Rewards Program Backend Deployment Script
# Usage: ./scripts/deploy.sh [environment] [options]
# Example: ./scripts/deploy.sh dev --require-approval never

set -e

# Default values
ENVIRONMENT=${1:-dev}
CDK_OPTIONS=${@:2}

# Validate environment
case $ENVIRONMENT in
  dev|staging|prod)
    echo "✅ Deploying to $ENVIRONMENT environment"
    ;;
  *)
    echo "❌ Invalid environment: $ENVIRONMENT"
    echo "Valid environments: dev, staging, prod"
    exit 1
    ;;
esac

# Set environment-specific variables
export ENVIRONMENT=$ENVIRONMENT

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}🚀 Starting deployment to $ENVIRONMENT environment${NC}"

# Check prerequisites
echo -e "${YELLOW}📋 Checking prerequisites...${NC}"

# Check if AWS CLI is installed and configured
if ! command -v aws &> /dev/null; then
    echo -e "${RED}❌ AWS CLI is not installed${NC}"
    exit 1
fi

# Check if CDK is installed
if ! command -v cdk &> /dev/null; then
    echo -e "${RED}❌ AWS CDK is not installed${NC}"
    exit 1
fi

# Check if Node.js dependencies are installed
if [ ! -d "node_modules" ]; then
    echo -e "${YELLOW}📦 Installing Node.js dependencies...${NC}"
    npm install
fi

# Check if Python dependencies are installed
if [ ! -d "lambda/venv" ]; then
    echo -e "${YELLOW}🐍 Setting up Python virtual environment...${NC}"
    cd lambda
    python3 -m venv venv
    source venv/bin/activate
    pip install -r requirements.txt
    cd ..
fi

# Build TypeScript
echo -e "${YELLOW}🔨 Building TypeScript...${NC}"
npm run build

# Run tests (optional, can be skipped with --skip-tests)
if [[ ! "$*" == *"--skip-tests"* ]]; then
    echo -e "${YELLOW}🧪 Running tests...${NC}"
    npm test
    
    # Run Python tests
    cd lambda
    source venv/bin/activate
    python -m pytest ../tests/ -v
    cd ..
fi

# Bootstrap CDK (if needed)
echo -e "${YELLOW}🏗️  Bootstrapping CDK (if needed)...${NC}"
cdk bootstrap --context environment=$ENVIRONMENT

# Synthesize CloudFormation template
echo -e "${YELLOW}📝 Synthesizing CloudFormation template...${NC}"
cdk synth --context environment=$ENVIRONMENT

# Deploy the stack
echo -e "${YELLOW}🚀 Deploying stack...${NC}"
cdk deploy --context environment=$ENVIRONMENT $CDK_OPTIONS

# Get stack outputs
echo -e "${YELLOW}📊 Getting stack outputs...${NC}"
STACK_NAME="rewards-${ENVIRONMENT}"
aws cloudformation describe-stacks --stack-name $STACK_NAME --query 'Stacks[0].Outputs' --output table

echo -e "${GREEN}✅ Deployment completed successfully!${NC}"
echo -e "${BLUE}📋 Next steps:${NC}"
echo "1. Verify the deployment in AWS Console"
echo "2. Test the API endpoints"
echo "3. Monitor CloudWatch dashboards and alarms"
echo "4. Check DLQ messages if any"

# Environment-specific post-deployment notes
case $ENVIRONMENT in
  prod)
    echo -e "${RED}⚠️  PRODUCTION DEPLOYMENT NOTES:${NC}"
    echo "- Monitor all alarms closely"
    echo "- Verify backup and recovery procedures"
    echo "- Check security configurations"
    echo "- Review access logs"
    ;;
  staging)
    echo -e "${YELLOW}📋 STAGING DEPLOYMENT NOTES:${NC}"
    echo "- Run integration tests"
    echo "- Verify performance benchmarks"
    echo "- Test disaster recovery procedures"
    ;;
  dev)
    echo -e "${BLUE}🔧 DEVELOPMENT DEPLOYMENT NOTES:${NC}"
    echo "- Resources will be destroyed on stack deletion"
    echo "- Use for testing and development only"
    ;;
esac