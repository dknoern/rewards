#!/bin/bash

# Deploy to Staging Environment
# This script deploys the rewards program backend to the staging environment
# with production-like settings for testing

set -e

echo "📋 Deploying to Staging Environment"
echo "⚠️  Note: This environment mirrors production settings"

# Require approval for staging deployments
./scripts/deploy.sh staging --require-approval broadening