---
inclusion: always
---

# Testing Guidelines

## Testing Strategy

- Write tests for all business logic and critical paths
- Aim for 80%+ code coverage on business logic
- Use pytest as the testing framework
- Follow the testing pyramid: many unit tests, fewer integration tests, minimal e2e tests
- Run tests automatically in CI/CD pipeline
- Use test fixtures and factories for test data
- Keep tests fast, isolated, and deterministic

## Unit Testing

- Test business logic in isolation from infrastructure
- Mock external dependencies (AWS services, APIs, databases)
- Use `moto` library for mocking AWS services
- Use `pytest-mock` for function mocking
- Test edge cases and error conditions
- Use parametrized tests for multiple input scenarios
- Follow AAA pattern: Arrange, Act, Assert
- One assertion per test when possible

## Integration Testing

- Test Lambda handlers with mocked AWS SDK calls
- Test API Gateway integration with Lambda
- Test event processing flows end-to-end
- Use LocalStack for local AWS service emulation when needed
- Test DynamoDB access patterns with local DynamoDB
- Verify error handling and retry logic
- Test idempotency of event handlers

## CDK Testing (TypeScript)

- Use CDK assertions library (`aws-cdk-lib/assertions`) to test infrastructure
- Use Jest as the testing framework for CDK code
- Verify resource creation and configuration
- Test IAM policies and permissions
- Validate resource tags and naming conventions
- Use snapshot tests for stack templates
- Test cross-stack references and dependencies
- Use `Template.fromStack()` for fine-grained assertions

## API Testing

- Test all API endpoints with various inputs
- Verify request validation and error responses
- Test authentication and authorization flows
- Validate response schemas and status codes
- Test rate limiting and throttling behavior
- Use tools like `requests` or `httpx` for API testing

## Test Organization

```
tests/
├── unit/           # Unit tests for business logic
├── integration/    # Integration tests
├── fixtures/       # Shared test fixtures
└── conftest.py     # Pytest configuration
```

## Best Practices

- Use descriptive test names that explain what is being tested
- Keep tests independent; avoid test interdependencies
- Clean up resources after tests (use fixtures with cleanup)
- Use factories for creating test objects (e.g., `factory_boy`)
- Separate test configuration from test code
- Use environment variables for test configuration
- Run tests in parallel when possible (`pytest-xdist`)
- Fail fast on critical test failures
