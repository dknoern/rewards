# Configuration Reference

## Overview

This document provides a comprehensive reference for all configuration options available in the Rewards Program Backend. The system uses environment-specific configuration to support different deployment scenarios (dev, staging, prod).

## Configuration Structure

### Configuration Files

#### `cdk.context.json`
Main configuration file containing environment-specific settings, naming conventions, and stack tags.

#### `bin/rewards.ts`
CDK application entry point that reads configuration and creates the stack with appropriate settings.

#### `lib/environment-config.ts`
TypeScript interfaces defining the configuration structure and types.

## Environment Configuration

### Configuration Schema

```typescript
interface EnvironmentConfig {
  account: string;                    // AWS account ID
  region: string;                     // AWS region
  removalPolicy: 'DESTROY' | 'RETAIN'; // Resource removal policy
  logRetention: number;               // Log retention in days
  enableDetailedMonitoring: boolean; // Enable detailed monitoring
  enableXRayTracing: boolean;        // Enable X-Ray tracing
  apiThrottling: {
    rateLimit: number;                // API requests per second
    burstLimit: number;               // API burst capacity
  };
  lambdaMemory: {
    query: number;                    // Query Lambda memory (MB)
    enrollment: number;               // Enrollment Lambda memory (MB)
    purchase: number;                 // Purchase Lambda memory (MB)
    redemption: number;               // Redemption Lambda memory (MB)
    tierEvaluation: number;           // Tier evaluation Lambda memory (MB)
    expiration: number;               // Expiration Lambda memory (MB)
  };
}
```

### Development Environment (`dev`)

```json
{
  "account": "123456789012",
  "region": "us-east-1",
  "removalPolicy": "DESTROY",
  "logRetention": 7,
  "enableDetailedMonitoring": false,
  "enableXRayTracing": true,
  "apiThrottling": {
    "rateLimit": 100,
    "burstLimit": 200
  },
  "lambdaMemory": {
    "query": 256,
    "enrollment": 256,
    "purchase": 256,
    "redemption": 256,
    "tierEvaluation": 512,
    "expiration": 512
  }
}
```

**Characteristics:**
- **Purpose**: Development and testing
- **Cost**: Optimized for low cost
- **Performance**: Basic performance settings
- **Durability**: Resources destroyed on stack deletion
- **Monitoring**: Basic monitoring only

### Staging Environment (`staging`)

```json
{
  "account": "123456789012",
  "region": "us-east-1",
  "removalPolicy": "RETAIN",
  "logRetention": 30,
  "enableDetailedMonitoring": true,
  "enableXRayTracing": true,
  "apiThrottling": {
    "rateLimit": 500,
    "burstLimit": 1000
  },
  "lambdaMemory": {
    "query": 512,
    "enrollment": 512,
    "purchase": 512,
    "redemption": 512,
    "tierEvaluation": 1024,
    "expiration": 1024
  }
}
```

**Characteristics:**
- **Purpose**: Pre-production testing
- **Cost**: Balanced cost and performance
- **Performance**: Production-like settings
- **Durability**: Resources retained on stack deletion
- **Monitoring**: Full monitoring enabled

### Production Environment (`prod`)

```json
{
  "account": "123456789012",
  "region": "us-east-1",
  "removalPolicy": "RETAIN",
  "logRetention": 90,
  "enableDetailedMonitoring": true,
  "enableXRayTracing": true,
  "apiThrottling": {
    "rateLimit": 1000,
    "burstLimit": 2000
  },
  "lambdaMemory": {
    "query": 512,
    "enrollment": 512,
    "purchase": 512,
    "redemption": 512,
    "tierEvaluation": 1024,
    "expiration": 1024
  }
}
```

**Characteristics:**
- **Purpose**: Production workloads
- **Cost**: Optimized for performance and reliability
- **Performance**: High performance settings
- **Durability**: All resources retained
- **Monitoring**: Comprehensive monitoring and alerting

## Naming Conventions

### Configuration Schema

```typescript
interface NamingConventions {
  stackName: string;      // CloudFormation stack name pattern
  resourcePrefix: string; // Prefix for resource names
  tableName: string;      // DynamoDB table name pattern
  eventBusName: string;   // EventBridge bus name pattern
  apiName: string;        // API Gateway name pattern
}
```

### Default Naming Patterns

```json
{
  "stackName": "rewards-${environment}",
  "resourcePrefix": "rewards-${environment}",
  "tableName": "rewards-program-${environment}",
  "eventBusName": "rewards-program-events-${environment}",
  "apiName": "rewards-program-api-${environment}"
}
```

### Resolved Names by Environment

#### Development
- **Stack**: `rewards-dev`
- **Table**: `rewards-program-dev`
- **Event Bus**: `rewards-program-events-dev`
- **API**: `rewards-program-api-dev`
- **Lambda Functions**: `rewards-{function}-handler-dev`

#### Staging
- **Stack**: `rewards-staging`
- **Table**: `rewards-program-staging`
- **Event Bus**: `rewards-program-events-staging`
- **API**: `rewards-program-api-staging`
- **Lambda Functions**: `rewards-{function}-handler-staging`

#### Production
- **Stack**: `rewards-prod`
- **Table**: `rewards-program-prod`
- **Event Bus**: `rewards-program-events-prod`
- **API**: `rewards-program-api-prod`
- **Lambda Functions**: `rewards-{function}-handler-prod`

## Stack Tags

### Configuration Schema

```json
{
  "stackTags": {
    "Project": "rewards-program",
    "Owner": "platform-team",
    "CostCenter": "customer-loyalty",
    "Environment": "${ENVIRONMENT}",
    "ManagedBy": "CDK"
  }
}
```

### Applied Tags by Environment

All resources are tagged with:
- **Project**: `rewards-program`
- **Owner**: `platform-team`
- **CostCenter**: `customer-loyalty`
- **Environment**: `dev` | `staging` | `prod`
- **ManagedBy**: `CDK`
- **DeployedBy**: Current user (added at deployment time)
- **DeployedAt**: Deployment timestamp (added at deployment time)

## Resource Configuration

### DynamoDB Table

#### Base Configuration
```typescript
{
  tableName: resolveName(namingConventions.tableName),
  partitionKey: { name: 'PK', type: STRING },
  sortKey: { name: 'SK', type: STRING },
  billingMode: PAY_PER_REQUEST,
  encryption: CUSTOMER_MANAGED,
  pointInTimeRecoveryEnabled: true,
  timeToLiveAttribute: 'ttl',
  removalPolicy: envConfig.removalPolicy
}
```

#### Global Secondary Indexes
- **GSI1**: `GSI1PK` (partition), `GSI1SK` (sort) - For tier-based queries
- **GSI2**: `GSI2PK` (partition), `GSI2SK` (sort) - For transaction idempotency

### Lambda Functions

#### Base Configuration
```typescript
{
  runtime: PYTHON_3_11,
  timeout: Duration.seconds(30), // 300 for batch functions
  memorySize: envConfig.lambdaMemory[functionType],
  tracing: envConfig.enableXRayTracing ? ACTIVE : DISABLED,
  retryAttempts: 2,
  environment: {
    TABLE_NAME: table.tableName,
    POWERTOOLS_SERVICE_NAME: functionName,
    LOG_LEVEL: 'INFO',
    ENVIRONMENT: environment
  }
}
```

#### Function-Specific Settings

| Function | Memory (dev) | Memory (staging/prod) | Timeout |
|----------|--------------|----------------------|---------|
| Query | 256 MB | 512 MB | 10s |
| Enrollment | 256 MB | 512 MB | 30s |
| Purchase | 256 MB | 512 MB | 30s |
| Redemption | 256 MB | 512 MB | 30s |
| Tier Evaluation | 512 MB | 1024 MB | 300s |
| Expiration | 512 MB | 1024 MB | 300s |

### API Gateway

#### Base Configuration
```typescript
{
  restApiName: resolveName(namingConventions.apiName),
  endpointType: REGIONAL,
  throttlingRateLimit: envConfig.apiThrottling.rateLimit,
  throttlingBurstLimit: envConfig.apiThrottling.burstLimit,
  loggingLevel: envConfig.enableDetailedMonitoring ? INFO : ERROR,
  dataTraceEnabled: envConfig.enableDetailedMonitoring
}
```

#### Throttling Settings

| Environment | Rate Limit | Burst Limit | Daily Quota |
|-------------|------------|-------------|-------------|
| dev | 100/sec | 200 | 10,000 |
| staging | 500/sec | 1,000 | 50,000 |
| prod | 1,000/sec | 2,000 | 100,000 |

### CloudWatch Logs

#### Retention Policies

| Environment | Retention Period | Purpose |
|-------------|------------------|---------|
| dev | 7 days | Short-term debugging |
| staging | 30 days | Integration testing |
| prod | 90 days | Compliance and audit |

#### Log Groups
- **Lambda Logs**: `/aws/lambda/rewards-{function}-handler-{environment}`
- **API Gateway Logs**: `/aws/apigateway/rewards-program-{environment}`

### EventBridge

#### Event Rules
- **Signup Events**: `rewards-signup-events-{environment}`
- **Purchase Events**: `rewards-purchase-events-{environment}`
- **Redemption Events**: `rewards-redemption-events-{environment}`
- **Tier Evaluation**: `rewards-tier-evaluation-schedule-{environment}`
- **Expiration**: `rewards-expiration-schedule-{environment}`

#### Scheduled Rules
- **Tier Evaluation**: Daily at 00:00 UTC
- **Star Expiration**: Daily at 01:00 UTC

### Dead Letter Queues

#### Configuration
```typescript
{
  queueName: `rewards-{function}-dlq-{environment}`,
  retentionPeriod: Duration.days(14),
  encryption: KMS_MANAGED
}
```

#### DLQ Names by Environment
- `rewards-enrollment-dlq-{environment}`
- `rewards-purchase-dlq-{environment}`
- `rewards-redemption-dlq-{environment}`
- `rewards-tier-evaluation-dlq-{environment}`
- `rewards-expiration-dlq-{environment}`

## Monitoring Configuration

### CloudWatch Dashboards

#### Main Dashboard
- **Name**: `rewards-program-overview-{environment}`
- **Widgets**: Lambda metrics, DynamoDB metrics, API Gateway metrics, DLQ metrics

#### Function Dashboards
- **Name Pattern**: `rewards-{function}-{environment}`
- **Functions**: enrollment, purchase, redemption, tier-evaluation, expiration, query

### CloudWatch Alarms

#### Critical Alarms
| Alarm | Threshold | Evaluation Periods | Actions |
|-------|-----------|-------------------|---------|
| DLQ Messages | ≥ 1 | 1 | SNS notification |
| Lambda Error Rate | > 5% | 2 | SNS notification |
| API 5XX Error Rate | > 1% | 2 | SNS notification |
| DynamoDB Throttling | ≥ 1 | 1 | SNS notification |
| Query P99 Latency | > 200ms | 2 | SNS notification |

#### Alarm Naming
- **Pattern**: `rewards-{metric}-{environment}`
- **Examples**: 
  - `rewards-enrollment-dlq-messages-prod`
  - `rewards-query-error-rate-prod`
  - `rewards-api-5xx-error-rate-prod`

## Security Configuration

### Encryption

#### DynamoDB
- **Encryption**: Customer-managed KMS key
- **Key Rotation**: Enabled
- **Key Description**: `KMS key for rewards program DynamoDB table encryption - {environment}`

#### SQS (DLQ)
- **Encryption**: KMS-managed keys
- **In-transit**: TLS 1.2+

### IAM Roles

#### Lambda Execution Roles
Each Lambda function has a dedicated IAM role with minimal required permissions:
- DynamoDB read/write access (scoped to rewards table)
- CloudWatch Logs write access
- X-Ray tracing permissions (if enabled)

#### API Gateway Role
- CloudWatch Logs write access for API access logging

### Network Security

#### API Gateway
- **CORS**: Configured for web client access
- **Endpoint Type**: Regional (not edge-optimized for security)
- **Request Validation**: Enabled for all endpoints

## Environment Variables

### Lambda Environment Variables

All Lambda functions receive these environment variables:

| Variable | Description | Example Value |
|----------|-------------|---------------|
| `TABLE_NAME` | DynamoDB table name | `rewards-program-prod` |
| `POWERTOOLS_SERVICE_NAME` | Service name for logging | `enrollment` |
| `LOG_LEVEL` | Logging level | `INFO` |
| `ENVIRONMENT` | Deployment environment | `prod` |

### CDK Context Variables

Set via command line or environment:

| Variable | Description | Default |
|----------|-------------|---------|
| `ENVIRONMENT` | Target environment | `dev` |
| `CDK_DEFAULT_ACCOUNT` | AWS account ID | From AWS credentials |
| `CDK_DEFAULT_REGION` | AWS region | From AWS credentials |

## Customization Guide

### Adding New Environment

1. **Add Environment Configuration**
   ```json
   // In cdk.context.json
   "environments": {
     "newenv": {
       "account": "123456789012",
       "region": "us-west-2",
       "removalPolicy": "RETAIN",
       // ... other settings
     }
   }
   ```

2. **Update Deployment Scripts**
   ```bash
   # Add validation in scripts/deploy.sh
   case $ENVIRONMENT in
     dev|staging|prod|newenv)
       echo "✅ Deploying to $ENVIRONMENT environment"
       ;;
   ```

3. **Create Environment-Specific Script**
   ```bash
   # Create scripts/deploy-newenv.sh
   ./scripts/deploy.sh newenv --require-approval broadening
   ```

### Modifying Resource Configuration

#### Lambda Memory Adjustment
```json
// In cdk.context.json
"lambdaMemory": {
  "query": 1024,  // Increased from 512
  "enrollment": 512,
  // ... other functions
}
```

#### API Throttling Adjustment
```json
// In cdk.context.json
"apiThrottling": {
  "rateLimit": 2000,  // Increased from 1000
  "burstLimit": 4000  // Increased from 2000
}
```

#### Log Retention Adjustment
```json
// In cdk.context.json
"logRetention": 180  // Increased from 90 days
```

### Adding New Configuration Options

1. **Update Interface**
   ```typescript
   // In lib/environment-config.ts
   interface EnvironmentConfig {
     // ... existing properties
     newOption: string;
   }
   ```

2. **Add to Context**
   ```json
   // In cdk.context.json
   "environments": {
     "prod": {
       // ... existing config
       "newOption": "value"
     }
   }
   ```

3. **Use in Stack**
   ```typescript
   // In lib/rewards-stack.ts
   const newValue = envConfig.newOption;
   ```

## Validation and Testing

### Configuration Validation

The CDK app validates configuration at synthesis time:
- Required environment configuration exists
- Account and region are specified
- Memory values are within Lambda limits
- Throttling values are positive numbers

### Testing Configuration Changes

1. **Synthesize Template**
   ```bash
   cdk synth --context environment=dev
   ```

2. **Diff Against Current**
   ```bash
   cdk diff --context environment=dev
   ```

3. **Deploy to Development**
   ```bash
   ./scripts/deploy-dev.sh
   ```

4. **Verify Configuration**
   ```bash
   source scripts/utils.sh
   check_stack_status dev
   ```

## Troubleshooting Configuration Issues

### Common Issues

#### Invalid Environment
```
Error: Environment configuration not found for: invalid
```
**Solution**: Check environment name in `cdk.context.json`

#### Missing Account/Region
```
Error: Cannot determine account and/or region
```
**Solution**: Set AWS credentials or specify in configuration

#### Invalid Memory Size
```
Error: Memory size must be between 128 and 10240 MB
```
**Solution**: Adjust `lambdaMemory` values in configuration

### Debugging Configuration

```bash
# Check current configuration
cdk context --clear  # Clear cached context
cdk synth --context environment=prod --verbose

# Validate JSON syntax
cat cdk.context.json | jq .

# Check environment variables
env | grep -E "(CDK|AWS|ENVIRONMENT)"
```