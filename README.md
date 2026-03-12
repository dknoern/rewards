# Rewards Program Backend

A serverless, event-driven rewards program backend built with AWS CDK, Lambda, DynamoDB, and EventBridge. The system manages member enrollment, star accrual from purchases, redemptions, and tier-based benefits across three membership tiers (Green, Gold, Reserve).

## 🏗️ Architecture

- **Event-Driven**: Uses Amazon EventBridge for asynchronous event processing
- **Serverless**: AWS Lambda functions for compute with automatic scaling
- **Single-Table Design**: DynamoDB with GSI indexes for efficient data access
- **RESTful API**: API Gateway for member balance and transaction queries
- **Monitoring**: Comprehensive CloudWatch dashboards and alarms
- **Multi-Environment**: Supports dev, staging, and production deployments

## 🚀 Quick Start

### Prerequisites

- Node.js 18+ and npm
- Python 3.11+
- AWS CLI v2 configured
- AWS CDK v2 installed globally

### Installation

```bash
# Clone repository
git clone <repository-url>
cd rewards-program-backend

# Install dependencies
npm install

# Set up Python environment
cd lambda
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cd ..

# Build TypeScript
npm run build
```

### Deploy to Development

```bash
# Quick development deployment
./scripts/deploy-dev.sh

# Or manual deployment
export ENVIRONMENT=dev
cdk bootstrap --context environment=dev
cdk deploy --context environment=dev --require-approval never
```

### Verify Deployment

```bash
# Check system status
source scripts/utils.sh
check_stack_status dev
run_smoke_tests dev
```

## 📋 System Components

### Lambda Functions

| Function | Purpose | Trigger | Memory | Timeout |
|----------|---------|---------|---------|---------|
| **Enrollment** | Process member signups | EventBridge | 256-512 MB | 30s |
| **Purchase** | Handle purchase events and star accrual | EventBridge | 256-512 MB | 30s |
| **Redemption** | Process star redemptions | EventBridge | 256-512 MB | 30s |
| **Tier Evaluation** | Daily tier promotions/demotions | Scheduled | 512-1024 MB | 300s |
| **Expiration** | Daily star expiration for Green members | Scheduled | 512-1024 MB | 300s |
| **Query** | API queries for member data | API Gateway | 256-512 MB | 10s |

### Data Model

#### DynamoDB Single-Table Design
- **Primary Key**: `PK` (partition), `SK` (sort)
- **GSI1**: Tier-based queries (`GSI1PK`, `GSI1SK`)
- **GSI2**: Transaction idempotency (`GSI2PK`, `GSI2SK`)

#### Access Patterns
- Get member profile: `PK=MEMBER#{id}`, `SK=PROFILE`
- Get member transactions: `PK=MEMBER#{id}`, `SK=TXN#{timestamp}`
- Query by tier: `GSI1PK=TIER#{tier}`, `GSI1SK=EVAL#{date}`
- Check idempotency: `GSI2PK=TXN#{txnId}`

### API Endpoints

- `GET /v1/members/{membershipId}` - Get member balance and status
- `GET /v1/members/{membershipId}/transactions` - Get transaction history

### Event Types

- `rewards.member.signup` - New member enrollment
- `rewards.transaction.purchase` - Purchase with star accrual
- `rewards.transaction.redemption` - Star redemption

## 🌍 Environments

### Development (`dev`)
- **Purpose**: Local development and testing
- **Resources**: Minimal memory, 7-day log retention
- **Removal Policy**: DESTROY (resources deleted on stack deletion)
- **API Throttling**: 100 req/sec, 200 burst

### Staging (`staging`)
- **Purpose**: Pre-production testing
- **Resources**: Production-like memory, 30-day log retention
- **Removal Policy**: RETAIN (resources preserved)
- **API Throttling**: 500 req/sec, 1000 burst

### Production (`prod`)
- **Purpose**: Live production environment
- **Resources**: Optimized memory, 90-day log retention
- **Removal Policy**: RETAIN (resources preserved)
- **API Throttling**: 1000 req/sec, 2000 burst

## 🔧 Configuration

Environment-specific configuration is managed in `cdk.context.json`:

```json
{
  "environments": {
    "dev": {
      "account": "123456789012",
      "region": "us-east-1",
      "removalPolicy": "DESTROY",
      "logRetention": 7,
      "enableDetailedMonitoring": false,
      "apiThrottling": { "rateLimit": 100, "burstLimit": 200 },
      "lambdaMemory": { "query": 256, "enrollment": 256, ... }
    }
  }
}
```

See [Configuration Reference](docs/CONFIGURATION.md) for complete details.

## 🚀 Deployment

### Environment-Specific Deployment

```bash
# Development (fast deployment)
./scripts/deploy-dev.sh

# Staging (requires approval for changes)
./scripts/deploy-staging.sh

# Production (requires confirmation and approval)
./scripts/deploy-prod.sh
```

### Manual Deployment

```bash
# Set target environment
export ENVIRONMENT=prod

# Deploy with specific options
cdk deploy --context environment=$ENVIRONMENT --require-approval any-change

# Deploy with change set review
cdk deploy --context environment=$ENVIRONMENT --no-execute
```

### Rollback

```bash
# Quick rollback to previous version
git checkout <previous-commit>
./scripts/deploy-prod.sh

# Emergency stack destruction (DANGEROUS)
./scripts/destroy.sh prod
```

## 📊 Monitoring

### CloudWatch Dashboards

- **Main Dashboard**: `rewards-program-overview-{environment}`
- **Function Dashboards**: `rewards-{function}-{environment}`

### Key Metrics

- Lambda invocations, errors, and duration
- API Gateway request count and latency
- DynamoDB capacity utilization and throttling
- Dead Letter Queue message counts

### Alarms

| Alarm | Threshold | Response Time |
|-------|-----------|---------------|
| DLQ Messages | ≥ 1 | Immediate (< 15 min) |
| Lambda Error Rate | > 5% | < 30 minutes |
| API 5XX Error Rate | > 1% | < 30 minutes |
| DynamoDB Throttling | ≥ 1 | < 15 minutes |
| Query P99 Latency | > 200ms | < 1 hour |

## 🛠️ Operations

### Daily Health Check

```bash
# Automated health check
source scripts/utils.sh
check_stack_status prod
check_dlq_messages prod
run_smoke_tests prod
```

### Common Tasks

```bash
# Check DLQ messages
check_dlq_messages prod

# Tail Lambda logs
tail_lambda_logs enrollment prod

# Get API endpoint
get_api_endpoint prod

# Monitor system performance
watch -n 30 'check_dlq_messages prod'
```

### Troubleshooting

```bash
# Check recent errors
aws logs filter-log-events \
  --log-group-name "/aws/lambda/rewards-query-handler-prod" \
  --filter-pattern "ERROR" \
  --start-time $(date -d '1 hour ago' +%s)000

# Check function configuration
aws lambda get-function --function-name rewards-query-handler-prod

# Review CloudFormation events
aws cloudformation describe-stack-events --stack-name rewards-prod
```

## 🧪 Testing

### Unit Tests

```bash
# Run Python tests
cd lambda
source venv/bin/activate
python -m pytest ../tests/unit/ -v

# Run TypeScript tests
npm test
```

### Integration Tests

```bash
# Run integration tests
python -m pytest tests/integration/ -v

# Run smoke tests against deployed environment
source scripts/utils.sh
run_smoke_tests dev
```

### Property-Based Tests

Property-based tests validate universal correctness properties:

```bash
# Run property tests with Hypothesis
python -m pytest tests/property/ -v --hypothesis-show-statistics
```

## 📚 Documentation

- [Deployment Guide](docs/DEPLOYMENT.md) - Comprehensive deployment instructions
- [Operations Guide](docs/OPERATIONS.md) - Monitoring and operational procedures
- [Runbook](docs/RUNBOOK.md) - Step-by-step operational procedures
- [Configuration Reference](docs/CONFIGURATION.md) - Complete configuration options

## 🏛️ Business Logic

### Membership Tiers

| Tier | Star Rate | Annual Threshold | Star Expiration |
|------|-----------|------------------|-----------------|
| **Green** | 1.0x | 0 stars | 6 months without activity |
| **Gold** | 1.2x | 500 stars | Never |
| **Reserve** | 1.7x | 2500 stars | Never |

### Star Multipliers

- **Double Star Day**: 2.0x multiplier
- **Personal Cup**: 2.0x multiplier
- **Combined**: Multipliers stack (e.g., 1.2 × 2.0 × 2.0 = 4.8x for Gold + Double Star + Personal Cup)

### Key Business Rules

1. **Enrollment**: New members start as Green tier with zero balance
2. **Tier Evaluation**: Daily evaluation at 00:00 UTC based on annual star count
3. **Star Expiration**: Daily expiration at 01:00 UTC for inactive Green members
4. **Redemption Minimum**: 60 stars minimum redemption
5. **Idempotency**: All events processed idempotently using transaction IDs

## 🔒 Security

### Data Protection

- **Encryption at Rest**: Customer-managed KMS keys for DynamoDB
- **Encryption in Transit**: TLS 1.2+ for all communications
- **Point-in-Time Recovery**: Enabled for DynamoDB table

### Access Control

- **IAM Roles**: Least privilege access for each Lambda function
- **API Security**: Request validation and CORS policies
- **Network Security**: Regional API Gateway endpoints

### Monitoring

- **CloudTrail**: All API activity logged
- **X-Ray Tracing**: Distributed tracing for performance and security monitoring
- **Structured Logging**: JSON-formatted logs with correlation IDs

## 🚨 Incident Response

### Severity Levels

- **Severity 1**: Complete system outage (< 15 min response)
- **Severity 2**: Degraded performance (< 1 hour response)
- **Severity 3**: Minor issues (next business day)

### Emergency Contacts

- **Primary On-Call**: [Contact Information]
- **Secondary On-Call**: [Contact Information]
- **Team Lead**: [Contact Information]

### Escalation Procedures

1. **Immediate**: Check system status and recent deployments
2. **Investigation**: Analyze logs and metrics
3. **Mitigation**: Implement temporary fixes
4. **Resolution**: Deploy permanent fixes
5. **Post-Incident**: Document lessons learned

## 🤝 Contributing

### Development Workflow

1. **Feature Branch**: Create feature branch from main
2. **Development**: Implement changes with tests
3. **Testing**: Run unit and integration tests
4. **Staging**: Deploy to staging environment
5. **Review**: Code review and approval
6. **Production**: Deploy to production

### Code Standards

- **Python**: PEP 8, type hints, docstrings
- **TypeScript**: Strict mode, explicit types
- **Testing**: 80%+ coverage for business logic
- **Documentation**: Update docs for all changes

## 📄 License

[License Information]

## 📞 Support

For support and questions:
- **Documentation**: Check docs/ directory
- **Issues**: Create GitHub issue
- **Emergency**: Contact on-call engineer
- **General**: Team Slack channel

---

**Built with ❤️ using AWS CDK, Lambda, DynamoDB, and EventBridge**