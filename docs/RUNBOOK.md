# Operational Runbook

## Overview

This runbook provides step-by-step procedures for common operational tasks and incident response scenarios for the Rewards Program Backend. Use this guide for quick reference during operational activities.

## Quick Reference Commands

### Environment Setup
```bash
# Source utility functions
source scripts/utils.sh

# Set environment
export ENVIRONMENT=prod  # or dev, staging
```

### System Status Checks
```bash
# Check overall system health
check_stack_status $ENVIRONMENT

# Check DLQ messages
check_dlq_messages $ENVIRONMENT

# Get API endpoint
get_api_endpoint $ENVIRONMENT

# Run smoke tests
run_smoke_tests $ENVIRONMENT
```

### Log Analysis
```bash
# Tail Lambda logs
tail_lambda_logs enrollment $ENVIRONMENT
tail_lambda_logs purchase $ENVIRONMENT
tail_lambda_logs redemption $ENVIRONMENT
tail_lambda_logs tier-evaluation $ENVIRONMENT
tail_lambda_logs expiration $ENVIRONMENT
tail_lambda_logs query $ENVIRONMENT

# Search for errors
aws logs filter-log-events \
  --log-group-name "/aws/lambda/rewards-enrollment-handler-$ENVIRONMENT" \
  --filter-pattern "ERROR" \
  --start-time $(date -d '1 hour ago' +%s)000
```

## Incident Response Procedures

### Incident Classification

#### Severity 1 - Critical (Production Down)
- **Response Time**: Immediate (< 15 minutes)
- **Examples**: Complete API failure, data corruption, security breach
- **Actions**: Page on-call engineer, engage incident commander

#### Severity 2 - High (Degraded Performance)
- **Response Time**: < 1 hour
- **Examples**: High error rates, slow response times, partial functionality loss
- **Actions**: Investigate and resolve, notify stakeholders

#### Severity 3 - Medium (Minor Issues)
- **Response Time**: Next business day
- **Examples**: Non-critical errors, minor performance issues
- **Actions**: Create ticket, schedule fix

### Incident Response Workflow

#### Step 1: Initial Assessment (0-5 minutes)
1. **Confirm the Issue**
   ```bash
   # Check system status
   check_stack_status prod
   run_smoke_tests prod
   ```

2. **Assess Impact**
   - Check CloudWatch dashboards
   - Review error rates and metrics
   - Determine affected functionality

3. **Classify Severity**
   - Use severity definitions above
   - Consider business impact
   - Determine response urgency

#### Step 2: Investigation (5-30 minutes)
1. **Check Recent Changes**
   ```bash
   # Review recent deployments
   aws cloudformation describe-stack-events --stack-name rewards-prod --max-items 20
   
   # Check git history
   git log --oneline -10
   ```

2. **Analyze Metrics and Logs**
   ```bash
   # Check DLQ messages
   check_dlq_messages prod
   
   # Review error logs
   aws logs filter-log-events \
     --log-group-name "/aws/lambda/rewards-query-handler-prod" \
     --filter-pattern "ERROR" \
     --start-time $(date -d '2 hours ago' +%s)000
   ```

3. **Identify Root Cause**
   - Code issues
   - Infrastructure problems
   - External dependencies
   - Capacity constraints

#### Step 3: Immediate Mitigation (30-60 minutes)
1. **For Code Issues**
   ```bash
   # Rollback deployment if recent
   git checkout <previous-commit>
   ./scripts/deploy-prod.sh
   ```

2. **For Capacity Issues**
   ```bash
   # Increase Lambda concurrency
   aws lambda put-provisioned-concurrency-config \
     --function-name rewards-query-handler-prod \
     --provisioned-concurrency-config ProvisionedConcurrencyUnits=10
   ```

3. **For DynamoDB Issues**
   ```bash
   # Check table status
   aws dynamodb describe-table --table-name rewards-program-prod
   
   # Enable auto-scaling if needed
   aws application-autoscaling register-scalable-target \
     --service-namespace dynamodb \
     --resource-id table/rewards-program-prod \
     --scalable-dimension dynamodb:table:WriteCapacityUnits \
     --min-capacity 5 \
     --max-capacity 100
   ```

#### Step 4: Resolution and Recovery (1-4 hours)
1. **Implement Permanent Fix**
   - Deploy code fixes
   - Adjust configurations
   - Scale resources appropriately

2. **Verify Resolution**
   ```bash
   # Run comprehensive tests
   run_smoke_tests prod
   
   # Monitor metrics for 30 minutes
   watch -n 30 'check_dlq_messages prod'
   ```

3. **Document Resolution**
   - Update incident ticket
   - Document root cause
   - Note lessons learned

## Common Operational Tasks

### Task 1: Deploy New Version

#### Prerequisites
- Code reviewed and approved
- Tests passing
- Staging deployment successful

#### Procedure
```bash
# 1. Backup current state
git tag backup-$(date +%Y%m%d-%H%M%S)

# 2. Deploy to production
./scripts/deploy-prod.sh

# 3. Verify deployment
check_stack_status prod
run_smoke_tests prod

# 4. Monitor for 30 minutes
watch -n 60 'check_dlq_messages prod'
```

#### Rollback if Issues
```bash
# Quick rollback
git checkout backup-<timestamp>
./scripts/deploy-prod.sh
```

### Task 2: Scale Lambda Functions

#### When to Scale
- High latency (P99 > 200ms)
- Throttling errors
- High concurrent executions

#### Procedure
```bash
# 1. Check current configuration
aws lambda get-function --function-name rewards-query-handler-prod

# 2. Update memory (increases CPU proportionally)
aws lambda update-function-configuration \
  --function-name rewards-query-handler-prod \
  --memory-size 1024

# 3. Set reserved concurrency if needed
aws lambda put-reserved-concurrency-config \
  --function-name rewards-query-handler-prod \
  --reserved-concurrency-units 100

# 4. Monitor performance
tail_lambda_logs query prod
```

### Task 3: Handle DLQ Messages

#### Investigation
```bash
# 1. Check message count
check_dlq_messages prod

# 2. Sample messages
aws sqs receive-message \
  --queue-url https://sqs.region.amazonaws.com/account/rewards-enrollment-dlq-prod \
  --max-number-of-messages 10 \
  --attribute-names All

# 3. Analyze message content
# Look for patterns in failed messages
```

#### Resolution
```bash
# For transient issues - redrive messages
aws sqs start-message-move-task \
  --source-arn arn:aws:sqs:region:account:rewards-enrollment-dlq-prod \
  --destination-arn arn:aws:sqs:region:account:rewards-enrollment-queue-prod

# For permanent issues - archive and purge
aws sqs receive-message \
  --queue-url https://sqs.region.amazonaws.com/account/rewards-enrollment-dlq-prod \
  --max-number-of-messages 10 > failed-messages-$(date +%Y%m%d).json

aws sqs purge-queue \
  --queue-url https://sqs.region.amazonaws.com/account/rewards-enrollment-dlq-prod
```

### Task 4: Database Maintenance

#### Check Table Health
```bash
# 1. Table status and metrics
aws dynamodb describe-table --table-name rewards-program-prod

# 2. Check consumed capacity
aws cloudwatch get-metric-statistics \
  --namespace AWS/DynamoDB \
  --metric-name ConsumedReadCapacityUnits \
  --dimensions Name=TableName,Value=rewards-program-prod \
  --start-time $(date -d '1 hour ago' --iso-8601) \
  --end-time $(date --iso-8601) \
  --period 300 \
  --statistics Sum
```

#### Optimize Performance
```bash
# 1. Enable auto-scaling
aws application-autoscaling register-scalable-target \
  --service-namespace dynamodb \
  --resource-id table/rewards-program-prod \
  --scalable-dimension dynamodb:table:ReadCapacityUnits \
  --min-capacity 5 \
  --max-capacity 100

# 2. Create scaling policy
aws application-autoscaling put-scaling-policy \
  --policy-name rewards-table-read-scaling-policy \
  --service-namespace dynamodb \
  --resource-id table/rewards-program-prod \
  --scalable-dimension dynamodb:table:ReadCapacityUnits \
  --policy-type TargetTrackingScaling \
  --target-tracking-scaling-policy-configuration file://scaling-policy.json
```

### Task 5: Monitor System Performance

#### Daily Health Check
```bash
#!/bin/bash
# Daily health check script

echo "=== Daily Health Check - $(date) ==="

# 1. System status
echo "1. System Status:"
check_stack_status prod

# 2. DLQ messages
echo "2. DLQ Status:"
check_dlq_messages prod

# 3. API health
echo "3. API Health:"
run_smoke_tests prod

# 4. Recent errors
echo "4. Recent Errors (last hour):"
aws logs filter-log-events \
  --log-group-name "/aws/lambda/rewards-query-handler-prod" \
  --filter-pattern "ERROR" \
  --start-time $(date -d '1 hour ago' +%s)000 \
  --query 'events[*].[logStreamName,message]' \
  --output table

echo "=== Health Check Complete ==="
```

#### Performance Analysis
```bash
# 1. Lambda performance metrics
aws cloudwatch get-metric-statistics \
  --namespace AWS/Lambda \
  --metric-name Duration \
  --dimensions Name=FunctionName,Value=rewards-query-handler-prod \
  --start-time $(date -d '24 hours ago' --iso-8601) \
  --end-time $(date --iso-8601) \
  --period 3600 \
  --statistics Average,Maximum \
  --output table

# 2. API Gateway metrics
aws cloudwatch get-metric-statistics \
  --namespace AWS/ApiGateway \
  --metric-name Latency \
  --dimensions Name=ApiName,Value=rewards-program-api-prod \
  --start-time $(date -d '24 hours ago' --iso-8601) \
  --end-time $(date --iso-8601) \
  --period 3600 \
  --statistics Average,Maximum \
  --output table
```

## Emergency Procedures

### Complete System Outage

#### Immediate Actions (0-15 minutes)
1. **Confirm Outage**
   ```bash
   run_smoke_tests prod
   check_stack_status prod
   ```

2. **Check AWS Service Health**
   - Visit AWS Service Health Dashboard
   - Check for regional outages
   - Verify account status

3. **Engage Incident Response**
   - Page on-call engineer
   - Start incident bridge
   - Notify stakeholders

#### Recovery Actions (15-60 minutes)
1. **Infrastructure Recovery**
   ```bash
   # Check CloudFormation stack
   aws cloudformation describe-stacks --stack-name rewards-prod
   
   # Redeploy if needed
   ./scripts/deploy-prod.sh
   ```

2. **Data Integrity Check**
   ```bash
   # Verify DynamoDB table
   aws dynamodb describe-table --table-name rewards-program-prod
   
   # Check recent backups
   aws dynamodb describe-continuous-backups --table-name rewards-program-prod
   ```

### Data Corruption Incident

#### Immediate Actions
1. **Stop Write Operations**
   ```bash
   # Disable EventBridge rules temporarily
   aws events disable-rule --name rewards-signup-events-prod
   aws events disable-rule --name rewards-purchase-events-prod
   aws events disable-rule --name rewards-redemption-events-prod
   ```

2. **Assess Damage**
   ```bash
   # Query affected data
   aws dynamodb scan --table-name rewards-program-prod --max-items 100
   ```

3. **Initiate Recovery**
   ```bash
   # Restore from point-in-time backup
   aws dynamodb restore-table-to-point-in-time \
     --source-table-name rewards-program-prod \
     --target-table-name rewards-program-prod-recovery \
     --restore-date-time <timestamp-before-corruption>
   ```

### Security Incident

#### Immediate Actions
1. **Isolate Affected Resources**
   ```bash
   # Disable API Gateway temporarily
   aws apigateway update-stage \
     --rest-api-id <api-id> \
     --stage-name v1 \
     --patch-ops op=replace,path=/throttle/rateLimit,value=0
   ```

2. **Review Access Logs**
   ```bash
   # Check CloudTrail for suspicious activity
   aws logs filter-log-events \
     --log-group-name CloudTrail/RewardsProgram \
     --start-time $(date -d '24 hours ago' +%s)000 \
     --filter-pattern "{ $.errorCode = \"*\" }"
   ```

3. **Rotate Credentials**
   ```bash
   # Rotate KMS keys
   aws kms schedule-key-deletion --key-id <key-id> --pending-window-in-days 7
   
   # Create new key
   aws kms create-key --description "Rewards Program Key - Rotated $(date)"
   ```

## Maintenance Windows

### Scheduled Maintenance Procedure

#### Pre-Maintenance (1 week before)
1. **Plan Maintenance**
   - Schedule maintenance window
   - Notify stakeholders
   - Prepare rollback plan

2. **Prepare Environment**
   - Test changes in staging
   - Backup current configuration
   - Prepare deployment scripts

#### During Maintenance
1. **Execute Changes**
   ```bash
   # Deploy updates
   ./scripts/deploy-prod.sh
   
   # Verify deployment
   check_stack_status prod
   run_smoke_tests prod
   ```

2. **Monitor System**
   ```bash
   # Watch for issues
   watch -n 30 'check_dlq_messages prod'
   
   # Monitor performance
   tail_lambda_logs query prod
   ```

#### Post-Maintenance
1. **Verify System Health**
   ```bash
   # Comprehensive health check
   run_smoke_tests prod
   check_stack_status prod
   ```

2. **Update Documentation**
   - Document changes made
   - Update runbooks if needed
   - Close maintenance tickets

## Troubleshooting Quick Reference

### High Error Rates
```bash
# 1. Check recent deployments
aws cloudformation describe-stack-events --stack-name rewards-prod --max-items 10

# 2. Review error logs
aws logs filter-log-events \
  --log-group-name "/aws/lambda/rewards-query-handler-prod" \
  --filter-pattern "ERROR" \
  --start-time $(date -d '2 hours ago' +%s)000

# 3. Check function configuration
aws lambda get-function --function-name rewards-query-handler-prod
```

### Slow Performance
```bash
# 1. Check Lambda duration
aws cloudwatch get-metric-statistics \
  --namespace AWS/Lambda \
  --metric-name Duration \
  --dimensions Name=FunctionName,Value=rewards-query-handler-prod \
  --start-time $(date -d '1 hour ago' --iso-8601) \
  --end-time $(date --iso-8601) \
  --period 300 \
  --statistics Average,Maximum

# 2. Check DynamoDB throttling
aws cloudwatch get-metric-statistics \
  --namespace AWS/DynamoDB \
  --metric-name ThrottledRequests \
  --dimensions Name=TableName,Value=rewards-program-prod \
  --start-time $(date -d '1 hour ago' --iso-8601) \
  --end-time $(date --iso-8601) \
  --period 300 \
  --statistics Sum
```

### DLQ Messages
```bash
# 1. Check all DLQs
check_dlq_messages prod

# 2. Sample messages from specific DLQ
aws sqs receive-message \
  --queue-url <dlq-url> \
  --max-number-of-messages 5 \
  --attribute-names All

# 3. Redrive messages if transient issue
aws sqs start-message-move-task \
  --source-arn <dlq-arn> \
  --destination-arn <main-queue-arn>
```

## Contact Information

### On-Call Rotation
- **Primary**: [Phone] [Email]
- **Secondary**: [Phone] [Email]
- **Escalation**: [Phone] [Email]

### Team Contacts
- **Team Lead**: [Contact Info]
- **DevOps**: [Contact Info]
- **Security**: [Contact Info]

### External Contacts
- **AWS Support**: [Case URL]
- **Vendor Support**: [Contact Info]

## Additional Resources

- [AWS Service Health Dashboard](https://status.aws.amazon.com/)
- [CloudWatch Console](https://console.aws.amazon.com/cloudwatch/)
- [DynamoDB Console](https://console.aws.amazon.com/dynamodb/)
- [Lambda Console](https://console.aws.amazon.com/lambda/)
- [API Gateway Console](https://console.aws.amazon.com/apigateway/)