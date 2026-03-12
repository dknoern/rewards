# Operations Guide

## Overview

This document provides operational procedures for monitoring, maintaining, and troubleshooting the Rewards Program Backend in production. It covers monitoring procedures, alarm response, DLQ message handling, and common operational tasks.

## System Architecture Overview

The Rewards Program Backend consists of:
- **6 Lambda Functions**: enrollment, purchase, redemption, tier-evaluation, expiration, query
- **1 DynamoDB Table**: Single-table design with GSI indexes
- **1 API Gateway**: RESTful API for member queries
- **1 EventBridge Bus**: Event-driven processing
- **5 DLQ Queues**: Dead letter queues for failed events
- **CloudWatch**: Monitoring, logging, and alerting

## Monitoring and Observability

### CloudWatch Dashboards

#### Main Dashboard: `rewards-program-overview-{environment}`
**Location**: CloudWatch Console → Dashboards
**Purpose**: High-level system health overview

**Key Widgets**:
- Lambda Functions Overview (invocations and errors)
- Lambda Duration (P99 latency)
- DynamoDB Metrics (capacity and throttling)
- API Gateway Metrics (requests and errors)
- EventBridge Metrics (rule invocations)
- DLQ Messages (all queues)

#### Individual Function Dashboards
**Naming**: `rewards-{function}-{environment}`
**Functions**: enrollment, purchase, redemption, tier-evaluation, expiration, query

**Key Widgets**:
- Invocations and Errors
- Duration (Average, P99, Maximum)
- Throttles and Concurrent Executions
- Memory Utilization

### Key Performance Indicators (KPIs)

#### System Health KPIs
- **Overall Error Rate**: < 1%
- **API Response Time**: P99 < 200ms
- **DynamoDB Throttling**: 0 events
- **DLQ Messages**: 0 messages

#### Business KPIs
- **Member Enrollment Rate**: Track daily enrollments
- **Purchase Processing Rate**: Track successful purchases
- **Redemption Success Rate**: Track successful redemptions
- **Tier Promotion Rate**: Track member promotions

### Alarm Configuration

#### Critical Alarms (Immediate Response Required)

1. **DLQ Message Alarms**
   - **Threshold**: ≥ 1 message
   - **Evaluation**: 1 period
   - **Response Time**: Immediate (< 15 minutes)

2. **Lambda Error Rate Alarms**
   - **Threshold**: > 5%
   - **Evaluation**: 2 periods
   - **Response Time**: < 30 minutes

3. **API Gateway 5XX Error Rate**
   - **Threshold**: > 1%
   - **Evaluation**: 2 periods
   - **Response Time**: < 30 minutes

4. **DynamoDB Throttling**
   - **Threshold**: ≥ 1 event
   - **Evaluation**: 1 period
   - **Response Time**: < 15 minutes

#### Warning Alarms (Monitor and Investigate)

1. **Query Handler P99 Latency**
   - **Threshold**: > 200ms
   - **Evaluation**: 2 periods
   - **Response Time**: < 1 hour

### Log Analysis

#### Log Locations
- **Lambda Logs**: `/aws/lambda/rewards-{function}-handler-{environment}`
- **API Gateway Logs**: `/aws/apigateway/rewards-program-{environment}`

#### Log Monitoring Commands
```bash
# Tail specific function logs
source scripts/utils.sh
tail_lambda_logs enrollment prod

# Search for errors in logs
aws logs filter-log-events --log-group-name "/aws/lambda/rewards-enrollment-handler-prod" --filter-pattern "ERROR"

# Get recent errors
aws logs filter-log-events --log-group-name "/aws/lambda/rewards-enrollment-handler-prod" --start-time $(date -d '1 hour ago' +%s)000 --filter-pattern "ERROR"
```

## Alarm Response Procedures

### DLQ Message Alarm Response

#### Immediate Actions (< 15 minutes)
1. **Identify Affected Queue**
   ```bash
   source scripts/utils.sh
   check_dlq_messages prod
   ```

2. **Check Message Count and Age**
   ```bash
   aws sqs get-queue-attributes --queue-url <queue-url> --attribute-names All
   ```

3. **Sample DLQ Messages**
   ```bash
   aws sqs receive-message --queue-url <queue-url> --max-number-of-messages 10
   ```

#### Investigation Steps
1. **Analyze Message Content**
   - Check for malformed event data
   - Verify required fields are present
   - Look for data type mismatches

2. **Check Lambda Function Logs**
   ```bash
   tail_lambda_logs <function-name> prod
   ```

3. **Identify Root Cause**
   - Code bugs in Lambda function
   - Invalid event schema
   - DynamoDB capacity issues
   - External service failures

#### Resolution Actions
1. **For Code Issues**
   - Deploy hotfix if critical
   - Schedule proper fix for next deployment

2. **For Data Issues**
   - Correct malformed events
   - Reprocess valid messages

3. **For Capacity Issues**
   - Increase DynamoDB capacity (if needed)
   - Scale Lambda concurrency

4. **Message Reprocessing**
   ```bash
   # Move messages back to main queue for reprocessing
   aws sqs redrive-allow-policy --queue-url <main-queue-url> --source-queue-arns <dlq-arn>
   ```

### Lambda Error Rate Alarm Response

#### Immediate Actions (< 30 minutes)
1. **Check Function Health**
   ```bash
   aws lambda get-function --function-name rewards-{function}-handler-prod
   ```

2. **Review Recent Deployments**
   - Check if error rate increased after recent deployment
   - Review CloudFormation stack events

3. **Analyze Error Patterns**
   ```bash
   aws logs filter-log-events --log-group-name "/aws/lambda/rewards-{function}-handler-prod" --filter-pattern "ERROR" --start-time $(date -d '1 hour ago' +%s)000
   ```

#### Investigation Steps
1. **Categorize Errors**
   - Validation errors (client-side issues)
   - Business logic errors (application issues)
   - Infrastructure errors (AWS service issues)

2. **Check Dependencies**
   - DynamoDB table health
   - EventBridge service status
   - Network connectivity

3. **Performance Analysis**
   - Check function duration trends
   - Memory utilization patterns
   - Concurrent execution limits

#### Resolution Actions
1. **For Application Errors**
   - Deploy hotfix for critical bugs
   - Increase error handling and validation

2. **For Infrastructure Errors**
   - Check AWS service health dashboard
   - Increase function timeout/memory if needed
   - Scale concurrency limits

3. **For Capacity Errors**
   - Increase Lambda reserved concurrency
   - Optimize function performance

### API Gateway Error Response

#### Immediate Actions (< 30 minutes)
1. **Check API Health**
   ```bash
   source scripts/utils.sh
   run_smoke_tests prod
   ```

2. **Review API Gateway Metrics**
   - Check request count trends
   - Analyze error distribution (4XX vs 5XX)
   - Review latency patterns

3. **Check Backend Lambda Health**
   ```bash
   tail_lambda_logs query prod
   ```

#### Investigation Steps
1. **Error Classification**
   - 4XX errors: Client-side issues (bad requests, authentication)
   - 5XX errors: Server-side issues (Lambda errors, timeouts)

2. **Request Analysis**
   - Check request patterns for anomalies
   - Verify request validation rules
   - Review authentication/authorization

3. **Performance Analysis**
   - API Gateway latency trends
   - Lambda cold start impacts
   - DynamoDB query performance

#### Resolution Actions
1. **For 4XX Errors**
   - Review API documentation
   - Improve request validation
   - Update client applications

2. **For 5XX Errors**
   - Fix Lambda function issues
   - Increase timeout values
   - Optimize database queries

### DynamoDB Throttling Response

#### Immediate Actions (< 15 minutes)
1. **Check Table Metrics**
   ```bash
   aws dynamodb describe-table --table-name rewards-program-prod
   ```

2. **Review Capacity Utilization**
   - Check consumed vs provisioned capacity
   - Analyze read/write patterns
   - Review GSI utilization

3. **Check Hot Partitions**
   - Look for uneven access patterns
   - Review partition key distribution

#### Investigation Steps
1. **Capacity Analysis**
   - Current capacity settings
   - Historical usage patterns
   - Peak usage times

2. **Access Pattern Review**
   - Query efficiency
   - Batch operation usage
   - Hot key identification

#### Resolution Actions
1. **Immediate Relief**
   - Enable auto-scaling (if not already enabled)
   - Temporarily increase capacity

2. **Long-term Optimization**
   - Optimize query patterns
   - Implement caching strategies
   - Review data model design

## DLQ Message Handling Procedures

### Message Analysis Workflow

1. **Retrieve Messages**
   ```bash
   aws sqs receive-message --queue-url <dlq-url> --attribute-names All --message-attribute-names All
   ```

2. **Analyze Message Structure**
   - Verify JSON format
   - Check required fields
   - Validate data types

3. **Categorize Issues**
   - **Transient**: Network timeouts, temporary service unavailability
   - **Permanent**: Invalid data format, business rule violations
   - **Configuration**: Wrong environment variables, missing permissions

### Message Reprocessing

#### For Transient Issues
```bash
# Redrive messages back to main queue
aws sqs start-message-move-task --source-arn <dlq-arn> --destination-arn <main-queue-arn>
```

#### For Correctable Issues
1. **Fix Data Issues**
   - Correct malformed JSON
   - Add missing required fields
   - Fix data type mismatches

2. **Resubmit Corrected Messages**
   ```bash
   aws events put-events --entries file://corrected-events.json
   ```

#### For Permanent Failures
1. **Document the Issue**
   - Record error details
   - Note business impact
   - Create improvement tickets

2. **Archive Messages**
   ```bash
   # Save messages for analysis
   aws sqs receive-message --queue-url <dlq-url> > failed-messages-$(date +%Y%m%d).json
   
   # Purge DLQ after archiving
   aws sqs purge-queue --queue-url <dlq-url>
   ```

## Routine Maintenance Tasks

### Daily Tasks

1. **Check System Health**
   ```bash
   source scripts/utils.sh
   check_stack_status prod
   check_dlq_messages prod
   ```

2. **Review CloudWatch Dashboards**
   - Check main dashboard for anomalies
   - Review error rates and latency trends
   - Verify all alarms are in OK state

3. **Monitor Business Metrics**
   - Daily enrollment numbers
   - Purchase processing volumes
   - Redemption success rates

### Weekly Tasks

1. **Performance Review**
   - Analyze weekly performance trends
   - Review capacity utilization
   - Check for optimization opportunities

2. **Log Analysis**
   - Review error patterns
   - Check for recurring issues
   - Analyze performance bottlenecks

3. **Security Review**
   - Check CloudTrail logs for unusual activity
   - Review IAM access patterns
   - Verify security configurations

### Monthly Tasks

1. **Capacity Planning**
   - Review growth trends
   - Plan capacity adjustments
   - Update auto-scaling policies

2. **Cost Optimization**
   - Analyze AWS costs
   - Identify optimization opportunities
   - Review resource utilization

3. **Backup Verification**
   - Test DynamoDB point-in-time recovery
   - Verify backup procedures
   - Update disaster recovery plans

## Troubleshooting Common Issues

### High Lambda Duration

#### Symptoms
- P99 latency > 200ms
- Timeout errors in logs
- Poor user experience

#### Investigation
1. **Check Memory Utilization**
   ```bash
   aws logs filter-log-events --log-group-name "/aws/lambda/rewards-query-handler-prod" --filter-pattern "REPORT"
   ```

2. **Analyze Cold Starts**
   - Check initialization duration
   - Review import statements
   - Optimize package size

3. **Database Query Performance**
   - Review DynamoDB query patterns
   - Check for full table scans
   - Optimize GSI usage

#### Resolution
1. **Increase Memory Allocation**
2. **Optimize Code Performance**
3. **Implement Connection Pooling**
4. **Add Caching Layer**

### DynamoDB Hot Partitions

#### Symptoms
- Throttling on specific operations
- Uneven capacity utilization
- Performance degradation

#### Investigation
1. **Analyze Access Patterns**
   - Check partition key distribution
   - Review query patterns
   - Identify hot keys

2. **Review Metrics**
   - Consumed capacity by operation
   - Throttling events by operation
   - Request patterns over time

#### Resolution
1. **Optimize Partition Key Design**
2. **Implement Request Spreading**
3. **Use Composite Keys**
4. **Add Caching Layer**

### EventBridge Processing Delays

#### Symptoms
- Events not processed timely
- Backlog in event processing
- Business process delays

#### Investigation
1. **Check Event Rules**
   ```bash
   aws events list-rules --event-bus-name rewards-program-events-prod
   ```

2. **Review Target Health**
   - Lambda function health
   - DLQ message counts
   - Processing rates

3. **Analyze Event Patterns**
   - Event volume trends
   - Processing time patterns
   - Error rates

#### Resolution
1. **Scale Lambda Concurrency**
2. **Optimize Event Processing**
3. **Implement Batch Processing**
4. **Add Circuit Breakers**

## Disaster Recovery Procedures

### Data Recovery

#### DynamoDB Point-in-Time Recovery
```bash
# List available recovery points
aws dynamodb describe-continuous-backups --table-name rewards-program-prod

# Restore to specific point in time
aws dynamodb restore-table-to-point-in-time \
  --source-table-name rewards-program-prod \
  --target-table-name rewards-program-prod-restored \
  --restore-date-time 2024-01-01T12:00:00.000Z
```

#### Infrastructure Recovery
```bash
# Redeploy infrastructure
./scripts/deploy-prod.sh

# Verify deployment
source scripts/utils.sh
check_stack_status prod
run_smoke_tests prod
```

### Business Continuity

1. **Identify Critical Functions**
   - Member enrollment
   - Purchase processing
   - Balance queries

2. **Implement Graceful Degradation**
   - Cache frequently accessed data
   - Implement retry mechanisms
   - Provide status pages

3. **Communication Plan**
   - Notify stakeholders
   - Update status pages
   - Provide regular updates

## Performance Optimization

### Lambda Optimization

1. **Memory Allocation**
   - Monitor memory utilization
   - Adjust based on performance needs
   - Balance cost vs performance

2. **Cold Start Reduction**
   - Minimize package size
   - Optimize imports
   - Use provisioned concurrency for critical functions

3. **Connection Management**
   - Reuse database connections
   - Implement connection pooling
   - Optimize SDK configurations

### DynamoDB Optimization

1. **Query Optimization**
   - Use appropriate indexes
   - Minimize data retrieved
   - Implement pagination

2. **Capacity Management**
   - Enable auto-scaling
   - Monitor utilization patterns
   - Optimize for cost-effectiveness

3. **Data Model Optimization**
   - Review access patterns
   - Optimize partition key design
   - Consider data archiving

## Security Operations

### Access Management

1. **Regular Access Reviews**
   - Review IAM policies
   - Audit user permissions
   - Remove unused access

2. **Key Rotation**
   - Rotate KMS keys annually
   - Update access keys regularly
   - Monitor key usage

### Monitoring and Alerting

1. **Security Alarms**
   - Unusual API access patterns
   - Failed authentication attempts
   - Privilege escalation attempts

2. **Compliance Monitoring**
   - Data access logging
   - Encryption verification
   - Backup compliance

## Contact Information

### Escalation Contacts

- **Primary On-Call**: [Contact Information]
- **Secondary On-Call**: [Contact Information]
- **Team Lead**: [Contact Information]
- **DevOps Team**: [Contact Information]

### Emergency Procedures

1. **Severity 1 (Critical)**
   - Contact primary on-call immediately
   - Escalate to team lead within 30 minutes
   - Engage DevOps team if infrastructure issue

2. **Severity 2 (High)**
   - Contact primary on-call within 1 hour
   - Document issue and resolution steps
   - Schedule follow-up review

3. **Severity 3 (Medium)**
   - Create ticket for next business day
   - Document issue details
   - Monitor for escalation