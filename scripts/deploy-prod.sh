#!/bin/bash

# Deploy to Production Environment
# This script deploys the rewards program backend to the production environment
# with strict approval requirements and safety checks

set -e

echo "🚨 PRODUCTION DEPLOYMENT"
echo "⚠️  WARNING: This will deploy to the production environment"
echo "📋 Please ensure:"
echo "   - All tests have passed"
echo "   - Code has been reviewed"
echo "   - Staging deployment was successful"
echo "   - Backup procedures are in place"
echo ""

# Prompt for confirmation
read -p "Are you sure you want to deploy to production? (yes/no): " -r
if [[ ! $REPLY =~ ^yes$ ]]; then
    echo "❌ Production deployment cancelled"
    exit 1
fi

echo "🚀 Proceeding with production deployment..."

# Require approval for all production changes
./scripts/deploy.sh prod --require-approval any-change

echo ""
echo "🎉 Production deployment completed!"
echo "📊 Please monitor:"
echo "   - CloudWatch dashboards"
echo "   - Application metrics"
echo "   - Error rates and alarms"
echo "   - DLQ messages"