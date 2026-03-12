#!/bin/bash

# Deploy to Development Environment
# This script deploys the rewards program backend to the dev environment
# with development-specific settings and minimal approval requirements

set -e

echo "🔧 Deploying to Development Environment"
echo "⚠️  Note: Resources will be destroyed when stack is deleted"

./scripts/deploy.sh dev --require-approval never --hotswap