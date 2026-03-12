# Deployment Guide

## Overview

This document provides comprehensive instructions for deploying the Rewards Program Backend to different environments (dev, staging, prod). The system uses AWS CDK for infrastructure as code and supports environment-specific configurations.

## Prerequisites

### Required Tools

- **Node.js** (v18 or later)
- **npm** (v8 or later)
- **Python** (v3.11 or later)
- **AWS CLI** (v2.x)
- **AWS CDK** (v2.x)

### AWS Account Setup

1. **AWS Account Access**: Ensure you have appropriate AWS credentials configured
2. **IAM Permissions**: Your AWS user/role must have permissions for:
   - CloudFormation (full access)
   - DynamoDB (full access)
   - Lambda (full access)
   - API Gateway (full access)
   - EventBridge (full access)
   - CloudWatch (full access)
   - IAM (role creation and policy attachment)
   - KMS (key creation and usage)

### Initial Setup

```bash
# Clone the repository
git clone <repository-url>
cd rewards-program-backend

# Install Node.js dependencies
npm install

# Set up Python virtual environment
cd lambda
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cd ..

# Build TypeScript
npm run build
```

## Environment Configuration

The system supports three environments with different configurations:

### Development (dev)
- **Purpose**: Local development and testing
- **Resources**: Minimal memory allocation, short log retention
- **Removal Policy**: DESTROY (resources deleted on stack deletion)
- **Monitoring**: Basic monitoring, X-Ray tracing enabled
- **API Throttling**: 100 req/sec, 200 burst

### Staging (staging)
- **Purpose**: Pre-production testing and validation
- **Resources**: Production-like memory allocation, medium log retention
- **Removal Policy**: RETAIN (resources preserved on stack deletion)
- **Monitoring**: Detailed monitoring enabled
- **API Throttling**: 500 req/sec, 1000 burst

### Production (prod)
- **Purpose**: Live production environment
- **Resources**: Optimized memory allocation, long log retention
- **Removal Policy**: RETAIN (resources preserved on stack deletion)
- **Monitoring**: Full monitoring and alerting
- **API Throttling**: 1000 req/sec, 2000 burst

## Deployment Process

### Quick Deployment

Use the provided deployment scripts for easy deployment:

```bash
# Development environment
./scripts/deploy-dev.sh

# Staging environment
./scripts/deploy-staging.sh

# Production environment (requires confirmation)
./scripts/deploy-prod.sh
```

### Manual Deployment

For more control over the deployment process:

```bash
# Set environment
export ENVIRONMENT=dev  # or staging, prod

# Bootstrap CDK (first time only)
cdk bootstrap --context environment=$ENVIRONMENT

# Synthesize template (optional, for review)
cdk synth --context environment=$ENVIRONMENT

# Deploy
cdk deploy --context environment=$ENVIRONMENT
```

### Deployment Options

#### Development Deployment
```bash
# Fast deployment with hotswap (dev only)
cdk deploy --context environment=dev --hotswap --require-approval never

# Skip tests for faster deployment
./scripts/deploy.sh dev --skip-tests --require-approval never
```

#### Staging Deployment
```bash
# Standard staging deployment
cdk deploy --context environment=staging --require-approval broadening
```

#### Production Deployment
```bash
# Production deployment with full approval
cdk deploy --context environment=prod --require-approval any-change

# Production deployment with change set review
cdk deploy --context environment=prod --require-approval any-change --no-execute
# Review the change set in AWS Console, then execute manually
```

## Post-Deployment Verification

### 1. Check Stack Status
```bash
# Using utility script
source scripts/utils.sh
check_stack_status prod

# Using AWS CLI directly
aws cloudformation describe-stacks --stack-name rewards-prod
```

### 2. Verify API Endpoints
```bash
# Get API endpoint
source scripts/utils.sh
get_api_endpoint prod

# Test API (replace with actual endpoint)
curl https://api-id.execute-api.region.amazonaws.com/v1/members/test-id
```

### 3. Check CloudWatch Dashboards
- Navigate to CloudWatch Console
- Check `rewards-program-overview-{environment}` dashboard
- Verify all widgets are displaying data

### 4. Verify Alarms
- Check CloudWatch Alarms
- Ensure all alarms are in OK state
- Verify SNS topic subscriptions

### 5. Test Event Processing
```bash
# Send test events to EventBridge (if test events are available)
aws events put-events --entries file://test-events.json
```

## Rollback Procedures

### Quick Rollback
If issues are detected immediately after deployment:

```bash
# Rollback to previous version
cdk deploy --context environment=prod --rollback
```

### Manual Rollback
1. Identify the previous working CloudFormation stack version
2. Use AWS Console to rollback the stack
3. Verify all services are functioning

### Emergency Rollback
For critical production issues:

```bash
# Destroy current stack (DANGEROUS - only for emergencies)
./scripts/destroy.sh prod

# Redeploy previous known-good version
git checkout <previous-commit>
./scripts/deploy-prod.sh
```

## Environment-Specific Considerations

### Development Environment
- Resources are automatically destroyed when stack is deleted
- Use for testing new features and configurations
- No data persistence guarantees
- Minimal monitoring and alerting

### Staging Environment
- Mirror production configuration
- Use for integration testing and performance validation
- Data is retained but can be reset as needed
- Full monitoring enabled for testing

### Production Environment
- **Critical**: All changes require approval
- Data is permanently retained
- Full backup and recovery procedures
- 24/7 monitoring and alerting
- Change management process required

## Troubleshooting

### Common Deployment Issues

#### 1. CDK Bootstrap Issues
```bash
# Error: "This stack uses assets, so the toolkit stack must be deployed"
cdk bootstrap --context environment=$ENVIRONMENT
```

#### 2. IAM Permission Issues
```bash
# Error: "User is not authorized to perform..."
# Ensure your AWS credentials have sufficient permissions
aws sts get-caller-identity
```

#### 3. Resource Conflicts
```bash
# Error: "Resource already exists"
# Check for existing resources with same names
aws cloudformation describe-stacks --stack-name rewards-$ENVIRONMENT
```

#### 4. Lambda Deployment Issues
```bash
# Error: "Code size exceeds maximum"
# Check lambda directory size
du -sh lambda/

# Clean up unnecessary files
cd lambda
find . -name "*.pyc" -delete
find . -name "__pycache__" -type d -exec rm -rf {} +
```

### Deployment Logs
Check CloudFormation events for detailed deployment progress:
```bash
aws cloudformation describe-stack-events --stack-name rewards-$ENVIRONMENT
```

### Lambda Function Issues
```bash
# Check function logs
source scripts/utils.sh
tail_lambda_logs enrollment prod

# Check function configuration
aws lambda get-function --function-name rewards-enrollment-handler-prod
```

## Security Considerations

### Deployment Security
- Use IAM roles with least privilege
- Enable CloudTrail for audit logging
- Rotate AWS access keys regularly
- Use MFA for production deployments

### Environment Isolation
- Each environment uses separate AWS resources
- No cross-environment resource sharing
- Environment-specific IAM roles and policies

### Secrets Management
- Use AWS Secrets Manager for sensitive data
- Never commit secrets to version control
- Rotate secrets regularly

## Monitoring and Alerting

### CloudWatch Dashboards
- **Main Dashboard**: `rewards-program-overview-{environment}`
- **Individual Function Dashboards**: `rewards-{function}-{environment}`

### Key Metrics to Monitor
- Lambda function invocations and errors
- API Gateway request count and latency
- DynamoDB read/write capacity and throttling
- DLQ message counts

### Alarm Thresholds
- Lambda error rate > 5%
- API Gateway 5XX error rate > 1%
- DynamoDB throttling events > 0
- Query handler P99 latency > 200ms
- Any DLQ messages > 0

## Backup and Recovery

### Automated Backups
- DynamoDB point-in-time recovery enabled
- CloudWatch logs retained per environment policy
- CloudFormation templates stored in version control

### Recovery Procedures
1. **Data Recovery**: Use DynamoDB point-in-time recovery
2. **Infrastructure Recovery**: Redeploy from CloudFormation template
3. **Configuration Recovery**: Restore from version control

## Change Management

### Development Changes
- Deploy directly to dev environment
- Test thoroughly before promoting

### Staging Changes
- Deploy to staging after dev testing
- Run full integration test suite
- Performance and load testing

### Production Changes
- Requires approval from team lead
- Deploy during maintenance window
- Monitor closely for 24 hours post-deployment
- Have rollback plan ready

## Support and Escalation

### Deployment Issues
1. Check deployment logs and CloudFormation events
2. Verify AWS credentials and permissions
3. Check for resource conflicts
4. Escalate to DevOps team if unresolved

### Production Issues
1. Check CloudWatch alarms and dashboards
2. Review application logs
3. Check DLQ messages
4. Follow incident response procedures
5. Escalate to on-call engineer if critical

## Additional Resources

- [AWS CDK Documentation](https://docs.aws.amazon.com/cdk/)
- [CloudFormation User Guide](https://docs.aws.amazon.com/cloudformation/)
- [AWS Lambda Developer Guide](https://docs.aws.amazon.com/lambda/)
- [API Gateway Developer Guide](https://docs.aws.amazon.com/apigateway/)
- [DynamoDB Developer Guide](https://docs.aws.amazon.com/dynamodb/)