# Rewards Program Lambda Functions

This directory contains the Python Lambda functions for the rewards program backend system.

## Structure

```
lambda/
├── common/                 # Shared utilities and modules
│   ├── models.py          # Pydantic data models
│   ├── validation.py      # Input validation utilities
│   └── dynamodb.py        # DynamoDB access layer
├── enrollment/            # Member enrollment handler
│   └── handler.py
├── purchase/              # Purchase transaction handler
│   └── handler.py
├── redemption/            # Star redemption handler
│   └── handler.py
├── query/                 # API Gateway query handler
│   └── handler.py
├── tier_evaluation/       # Scheduled tier evaluation handler
│   └── handler.py
├── expiration/            # Scheduled star expiration handler
│   └── handler.py
├── requirements.txt       # Python dependencies
└── runtime.txt           # Python runtime version
```

## Runtime

- Python 3.11+

## Dependencies

Core dependencies:
- `boto3` - AWS SDK for Python
- `pydantic` - Data validation and models
- `hypothesis` - Property-based testing framework
- `pytest` - Testing framework
- `moto` - AWS service mocking for tests

## Installation

Install dependencies locally for development:

```bash
cd lambda
pip install -r requirements.txt
```

## Lambda Handlers

Each Lambda function has a `handler.py` file with a `handler(event, context)` function:

- **enrollment/handler.py**: Processes member signup events from EventBridge
- **purchase/handler.py**: Processes purchase transaction events, calculates stars
- **redemption/handler.py**: Processes star redemption events
- **query/handler.py**: Handles API Gateway requests for member data
- **tier_evaluation/handler.py**: Scheduled handler for tier promotions/demotions
- **expiration/handler.py**: Scheduled handler for Green tier star expiration

## Shared Modules

### common/models.py

Pydantic models for:
- Member profiles
- Transactions
- Event payloads
- API responses

### common/validation.py

Input validation utilities:
- Event message validation
- Data type validation
- Error response formatting

### common/dynamodb.py

DynamoDB access layer:
- Member CRUD operations
- Transaction recording
- Star ledger management
- Idempotency checks

## Environment Variables

Lambda functions expect these environment variables:
- `TABLE_NAME`: DynamoDB table name (default: `rewards-program`)

## Testing

Tests are organized in the `tests/` directory at the project root:

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=lambda --cov-report=html

# Run property-based tests
pytest tests/property/
```

## Deployment

Lambda functions are deployed via AWS CDK. See `lib/rewards-stack.ts` for infrastructure configuration.
