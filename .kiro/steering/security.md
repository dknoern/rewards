---
inclusion: always
---

# Security Guidelines

## Authentication & Authorization

- Use Amazon Cognito for user authentication
- Implement JWT token validation in API Gateway authorizers
- Use IAM roles and policies for service-to-service authentication
- Follow principle of least privilege for all IAM permissions
- Use resource-based policies where appropriate
- Implement API key rotation for third-party integrations
- Use AWS Secrets Manager for sensitive credentials
- Never hardcode credentials or secrets in code

## API Security

- Enable AWS WAF on API Gateway for DDoS protection
- Implement request validation and input sanitization
- Use CORS policies restrictively
- Enable API Gateway access logging to CloudWatch
- Implement rate limiting per client/API key
- Use VPC endpoints for private API access
- Enable API Gateway caching with appropriate TTLs
- Validate all input data against schemas

## Data Security

- Encrypt all data at rest using AWS KMS
- Use TLS 1.2+ for all data in transit
- Enable S3 bucket encryption and block public access
- Use VPC for network isolation of resources
- Enable DynamoDB point-in-time recovery for critical tables
- Implement data retention and deletion policies
- Use AWS Backup for automated backup strategies
- Mask or tokenize PII in logs and non-production environments

## Lambda Security

- Use separate IAM roles per Lambda function
- Enable Lambda function URL authentication when used
- Set appropriate timeout and memory limits
- Use environment variables for configuration, Secrets Manager for secrets
- Enable X-Ray tracing for security monitoring
- Keep Lambda layers and dependencies updated
- Use VPC only when necessary (adds cold start latency)
- Implement input validation at function entry points

## Monitoring & Compliance

- Enable CloudTrail for all API activity logging
- Use AWS Config for compliance monitoring
- Set up CloudWatch alarms for security events
- Implement centralized logging with log retention policies
- Use AWS Security Hub for security posture management
- Regularly scan dependencies for vulnerabilities
- Implement automated security testing in CI/CD pipeline
