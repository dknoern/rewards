# Implementation Plan: Rewards Program Backend

## Overview

This implementation plan breaks down the rewards program backend into discrete coding tasks. The system uses an event-driven serverless architecture with AWS Lambda (Python 3.11+), EventBridge, DynamoDB, and API Gateway. Infrastructure is defined using AWS CDK (TypeScript).

The implementation follows an incremental approach: infrastructure setup → core Lambda handlers → event processing → testing → integration. Each task builds on previous work, with checkpoints to validate progress.

## Tasks

- [x] 1. Set up project structure and CDK infrastructure foundation
  - [x] 1.1 Initialize CDK project with TypeScript
    - Create CDK app structure with `cdk init app --language typescript`
    - Configure tsconfig.json with strict mode enabled
    - Set up project dependencies (aws-cdk-lib, constructs)
    - Create directory structure: `lib/` for CDK stacks, `lambda/` for Python handlers
    - _Requirements: All (infrastructure foundation)_

  - [x] 1.2 Create DynamoDB table with single-table design
    - Define table with PK (string) and SK (string) in CDK
    - Configure GSI1 (GSI1PK, GSI1SK) for tier-based queries
    - Configure GSI2 (GSI2PK, GSI2SK) for transaction idempotency lookups
    - Enable point-in-time recovery and encryption at rest with KMS
    - Set billing mode to PAY_PER_REQUEST
    - Add resource tags (environment, service, cost-center)
    - _Requirements: 1.1, 2.3, 4.5, 10.4, 11.1-11.5_

  - [x] 1.3 Create EventBridge event bus and rules
    - Define custom event bus for rewards events
    - Create event rules for signup, purchase, and redemption event types
    - Configure scheduled rules for tier evaluation (daily at 00:00 UTC)
    - Configure scheduled rules for expiration handler (daily at 01:00 UTC)
    - _Requirements: 1.1, 2.1, 4.1, 5.5, 6.2_

  - [x] 1.4 Create API Gateway REST API
    - Define REST API with regional endpoint
    - Configure CORS policies
    - Enable access logging to CloudWatch
    - Set up request validation
    - Configure throttling and rate limiting
    - _Requirements: 8.1-8.5_

  - [x] 1.5 Set up Python Lambda project structure
    - Create `lambda/` directory with subdirectories for each handler
    - Set up requirements.txt with dependencies (boto3, hypothesis for testing)
    - Create shared modules: `common/models.py`, `common/validation.py`, `common/dynamodb.py`
    - Configure Python 3.11 runtime settings
    - _Requirements: All (code foundation)_

- [x] 2. Implement event schema validation and shared utilities
  - [x] 2.1 Create event schema validation module
    - Define Pydantic models for signup, purchase, and redemption events
    - Implement validation for required fields and data types
    - Add validation for negative amounts (purchase and redemption)
    - Create error response formatter with standardized error codes
    - _Requirements: 9.1-9.5_

  - [ ]* 2.2 Write property test for event validation
    - **Property 18: Event Message Validation**
    - **Validates: Requirements 9.1, 9.2, 9.3**

  - [x] 2.3 Create DynamoDB access layer
    - Implement helper functions for get_member, update_member, create_transaction
    - Add conditional update logic for atomic balance modifications
    - Implement query functions for GSI1 (tier queries) and GSI2 (idempotency)
    - Add error handling for DynamoDB exceptions
    - _Requirements: 1.1, 2.5, 4.4, 10.2_

  - [x] 2.4 Implement idempotency checker
    - Create function to check transaction ID in GSI2
    - Implement TTL-based cleanup (30 days)
    - Return cached result for duplicate transaction IDs
    - _Requirements: 10.1-10.4_

  - [ ]* 2.5 Write property tests for idempotency
    - **Property 19: Idempotent Event Processing**
    - **Validates: Requirements 10.1, 10.2, 10.3**
    - **Property 20: Transaction Identifier Retention**
    - **Validates: Requirements 10.4**

- [x] 3. Checkpoint - Validate infrastructure and shared utilities
  - Ensure CDK synth succeeds without errors
  - Verify DynamoDB table schema matches design
  - Run unit tests for validation and DynamoDB modules
  - Ensure all tests pass, ask the user if questions arise

- [x] 4. Implement enrollment handler Lambda function
  - [x] 4.1 Create enrollment handler with event processing
    - Parse and validate signup event message
    - Generate unique membership ID (UUID)
    - Check for duplicate enrollment using membership ID
    - Create member profile record with Green tier, zero balance
    - Record enrollment timestamp and set initial tier evaluation date
    - Implement idempotency using transaction ID
    - _Requirements: 1.1-1.5_

  - [ ]* 4.2 Write property tests for enrollment
    - **Property 1: Member Enrollment Creates Valid Profile**
    - **Validates: Requirements 1.1, 1.2, 1.3, 1.4**
    - **Property 2: Duplicate Enrollment Rejection**
    - **Validates: Requirements 1.5**

  - [ ]* 4.3 Write unit tests for enrollment handler
    - Test successful enrollment with valid data
    - Test duplicate enrollment rejection
    - Test missing required fields error
    - Test idempotent duplicate transaction ID handling
    - _Requirements: 1.1-1.5_

  - [x] 4.4 Create CDK construct for enrollment Lambda
    - Define Lambda function with Python 3.11 runtime
    - Configure IAM role with DynamoDB write permissions
    - Set memory to 512MB and timeout to 30 seconds
    - Configure environment variables (table name)
    - Add EventBridge rule target for signup events
    - Configure DLQ with CloudWatch alarm
    - Enable X-Ray tracing
    - _Requirements: 1.1_

- [x] 5. Implement purchase handler Lambda function
  - [x] 5.1 Create star calculation logic
    - Implement tier-based rate calculation (Green: 1.0, Gold: 1.2, Reserve: 1.7)
    - Add double star day multiplier (2.0x)
    - Add personal cup multiplier (2.0x)
    - Handle combined multipliers correctly
    - _Requirements: 2.4, 3.1-3.5_

  - [ ]* 5.2 Write property tests for star calculation
    - **Property 5: Tier-Based Star Calculation**
    - **Validates: Requirements 2.4, 3.1, 3.2, 3.3**
    - **Property 6: Double Star Day Multiplier**
    - **Validates: Requirements 3.4**
    - **Property 7: Personal Cup Multiplier**
    - **Validates: Requirements 3.5**

  - [x] 5.3 Create purchase handler with event processing
    - Parse and validate purchase event message
    - Validate membership ID exists
    - Calculate stars using tier rate and multipliers
    - Update star balance atomically with conditional update
    - Update last qualifying activity timestamp
    - Update annual star count
    - Create star ledger entry for Green members
    - Record purchase transaction with all details
    - Implement idempotency using transaction ID
    - _Requirements: 2.1-2.6, 3.1-3.5, 6.1_

  - [ ]* 5.4 Write property tests for purchase processing
    - **Property 3: Invalid Membership ID Rejection**
    - **Validates: Requirements 2.1, 2.2**
    - **Property 4: Purchase Updates Balance and Activity**
    - **Validates: Requirements 2.3, 2.5, 2.6**
    - **Property 11: Green Member Star Tracking**
    - **Validates: Requirements 6.1**

  - [ ]* 5.5 Write unit tests for purchase handler
    - Test successful purchase for each tier
    - Test double star day calculation
    - Test personal cup calculation
    - Test combined multipliers
    - Test invalid membership ID error
    - Test negative amount validation
    - Test idempotent processing
    - _Requirements: 2.1-2.6, 3.1-3.5_

  - [x] 5.6 Create CDK construct for purchase Lambda
    - Define Lambda function with Python 3.11 runtime
    - Configure IAM role with DynamoDB read/write permissions
    - Set memory to 512MB and timeout to 30 seconds
    - Configure environment variables (table name)
    - Add EventBridge rule target for purchase events
    - Configure DLQ with CloudWatch alarm
    - Enable X-Ray tracing
    - _Requirements: 2.1_

- [x] 6. Checkpoint - Validate enrollment and purchase handlers
  - Deploy CDK stack to test environment
  - Test enrollment flow with sample events
  - Test purchase flow for all tiers
  - Verify DynamoDB records created correctly
  - Ensure all tests pass, ask the user if questions arise

- [x] 7. Implement redemption handler Lambda function
  - [x] 7.1 Create redemption handler with validation
    - Parse and validate redemption event message
    - Validate membership ID exists
    - Validate star balance is sufficient (conditional update)
    - Validate minimum redemption threshold (60 stars)
    - Deduct stars atomically from balance
    - Record redemption transaction with item description
    - Implement idempotency using transaction ID
    - _Requirements: 4.1-4.6_

  - [ ]* 7.2 Write property tests for redemption
    - **Property 8: Redemption Validation and Processing**
    - **Validates: Requirements 4.2, 4.3, 4.4, 4.5**

  - [ ]* 7.3 Write unit tests for redemption handler
    - Test successful redemption with sufficient balance
    - Test insufficient balance error
    - Test redemption at exactly 60 stars (minimum)
    - Test redemption at exactly current balance
    - Test invalid membership ID error
    - Test negative redemption amount validation
    - Test idempotent processing
    - _Requirements: 4.1-4.6_

  - [x] 7.4 Create CDK construct for redemption Lambda
    - Define Lambda function with Python 3.11 runtime
    - Configure IAM role with DynamoDB read/write permissions
    - Set memory to 512MB and timeout to 30 seconds
    - Configure environment variables (table name)
    - Add EventBridge rule target for redemption events
    - Configure DLQ with CloudWatch alarm
    - Enable X-Ray tracing
    - _Requirements: 4.1_

- [x] 8. Implement tier evaluation handler Lambda function
  - [x] 8.1 Create tier evaluation logic
    - Query all members using GSI1 where next evaluation date has passed
    - Calculate annual star count from transactions in past 12 months
    - Determine new tier based on thresholds (500 → Gold, 2500 → Reserve)
    - Handle demotion for members below thresholds after 12 months
    - Update member tier, tier timestamp, and next evaluation date
    - Remove expiration dates from star ledger when promoting from Green
    - Record tier change transaction
    - _Requirements: 5.1-5.5, 7.3_

  - [ ]* 8.2 Write property tests for tier evaluation
    - **Property 9: Tier Promotion at Thresholds**
    - **Validates: Requirements 5.1, 5.2, 5.3, 5.4**
    - **Property 10: Tier Recalculation After Evaluation Period**
    - **Validates: Requirements 5.5**
    - **Property 15: Promotion Removes Expiration Dates**
    - **Validates: Requirements 7.3**

  - [ ]* 8.3 Write unit tests for tier evaluation handler
    - Test promotion to Gold at 500 stars
    - Test promotion to Reserve at 2500 stars
    - Test no promotion below thresholds
    - Test demotion after 12-month period
    - Test expiration date removal on promotion
    - Test tier change transaction recording
    - _Requirements: 5.1-5.5, 7.3_

  - [x] 8.4 Create CDK construct for tier evaluation Lambda
    - Define Lambda function with Python 3.11 runtime
    - Configure IAM role with DynamoDB read/write permissions
    - Set memory to 1024MB and timeout to 300 seconds (batch processing)
    - Configure environment variables (table name)
    - Add EventBridge scheduled rule (daily at 00:00 UTC)
    - Configure DLQ with CloudWatch alarm
    - Enable X-Ray tracing
    - _Requirements: 5.1_

- [x] 9. Implement expiration handler Lambda function
  - [x] 9.1 Create expiration logic for Green members
    - Query all Green tier members using GSI1
    - For each member, check last qualifying activity timestamp
    - If no activity in past month, query star ledger entries
    - Expire stars older than 6 months
    - Deduct expired stars from balance atomically
    - Delete expired star ledger entries
    - Record expiration transaction
    - _Requirements: 6.2-6.5_

  - [ ]* 9.2 Write property tests for expiration
    - **Property 12: Star Expiration for Inactive Green Members**
    - **Validates: Requirements 6.2, 6.4, 6.5**
    - **Property 13: Activity Resets Expiration Timer**
    - **Validates: Requirements 6.3**
    - **Property 14: Non-Expiring Stars for Gold and Reserve**
    - **Validates: Requirements 7.1, 7.2**

  - [ ]* 9.3 Write unit tests for expiration handler
    - Test expiration for inactive Green member (no activity in 6+ months)
    - Test no expiration for active Green member (recent activity)
    - Test no expiration for Gold members
    - Test no expiration for Reserve members
    - Test expiration transaction recording
    - Test balance update after expiration
    - _Requirements: 6.2-6.5, 7.1-7.2_

  - [x] 9.4 Create CDK construct for expiration Lambda
    - Define Lambda function with Python 3.11 runtime
    - Configure IAM role with DynamoDB read/write permissions
    - Set memory to 1024MB and timeout to 300 seconds (batch processing)
    - Configure environment variables (table name)
    - Add EventBridge scheduled rule (daily at 01:00 UTC)
    - Configure DLQ with CloudWatch alarm
    - Enable X-Ray tracing
    - _Requirements: 6.2_

- [x] 10. Checkpoint - Validate tier evaluation and expiration handlers
  - Deploy updated CDK stack
  - Test tier evaluation with sample members at thresholds
  - Test expiration logic with inactive Green members
  - Verify scheduled rules trigger correctly
  - Ensure all tests pass, ask the user if questions arise

- [x] 11. Implement query handler Lambda function and API endpoints
  - [x] 11.1 Create query handler for member balance
    - Implement GET /v1/members/{membershipId} endpoint
    - Validate membership ID format
    - Fetch member profile from DynamoDB
    - Return member data (balance, tier, annual count, timestamps)
    - Handle member not found error
    - Optimize for sub-200ms response time
    - _Requirements: 8.1-8.5_

  - [x] 11.2 Create query handler for transaction history
    - Implement GET /v1/members/{membershipId}/transactions endpoint
    - Query transactions using PK=MEMBER#{id} and SK begins_with TXN#
    - Implement pagination with limit and nextToken
    - Return transactions in chronological order
    - Include all transaction types (purchase, redemption, tier change, expiration)
    - _Requirements: 11.1-11.5_

  - [ ]* 11.3 Write property tests for query handlers
    - **Property 16: Member Query Returns Complete Data**
    - **Validates: Requirements 8.1, 8.2, 8.3**
    - **Property 17: Invalid Query Rejection**
    - **Validates: Requirements 8.4**
    - **Property 21: Complete Transaction History**
    - **Validates: Requirements 11.1, 11.2, 11.3, 11.4, 11.5**

  - [ ]* 11.4 Write unit tests for query handler
    - Test successful member query with valid ID
    - Test member not found error
    - Test transaction history query with pagination
    - Test empty transaction history
    - Test response time under 200ms (performance test)
    - _Requirements: 8.1-8.5, 11.1-11.5_

  - [x] 11.5 Create CDK construct for query Lambda and API integration
    - Define Lambda function with Python 3.11 runtime
    - Configure IAM role with DynamoDB read-only permissions
    - Set memory to 512MB and timeout to 10 seconds
    - Configure environment variables (table name)
    - Create API Gateway resources and methods
    - Add Lambda proxy integration
    - Configure request/response models
    - Enable API caching with 60-second TTL
    - _Requirements: 8.1_

- [x] 12. Implement monitoring, alarms, and observability
  - [x] 12.1 Create CloudWatch dashboards
    - Add metrics for Lambda invocations, errors, duration
    - Add metrics for DynamoDB read/write capacity and throttles
    - Add metrics for API Gateway requests, latency, 4xx/5xx errors
    - Add metrics for EventBridge rule invocations
    - Create dashboard for each Lambda function
    - _Requirements: All (operational visibility)_

  - [x] 12.2 Configure CloudWatch alarms
    - Create alarms for DLQ message count > 0 (all handlers)
    - Create alarms for Lambda error rate > 5%
    - Create alarms for API Gateway 5xx error rate > 1%
    - Create alarms for DynamoDB throttling events
    - Create alarms for query handler P99 latency > 200ms
    - Configure SNS topic for alarm notifications
    - _Requirements: All (operational health)_

  - [x] 12.3 Enable X-Ray tracing and structured logging
    - Configure X-Ray tracing for all Lambda functions
    - Add structured logging with JSON format
    - Include correlation IDs in all log entries
    - Add log sampling for high-volume operations
    - Configure log retention policies (30 days)
    - _Requirements: All (debugging and troubleshooting)_

- [ ]* 13. Write integration tests for end-to-end flows
  - [ ]* 13.1 Test complete enrollment-to-redemption flow
    - Enroll member → Purchase → Verify balance → Redeem → Verify balance
    - Test with all three tiers
    - Verify transaction history completeness
    - _Requirements: 1.1-1.5, 2.1-2.6, 4.1-4.6, 11.1-11.5_

  - [ ]* 13.2 Test tier promotion flow
    - Enroll member → Multiple purchases to reach 500 stars → Trigger tier evaluation → Verify Gold promotion
    - Verify expiration dates removed from star ledger
    - _Requirements: 5.1-5.5, 7.3_

  - [ ]* 13.3 Test expiration flow for Green members
    - Enroll member → Purchase → Wait 6 months (simulated) → No activity → Trigger expiration → Verify balance reduced
    - Test activity resets expiration timer
    - _Requirements: 6.1-6.5_

  - [ ]* 13.4 Test idempotency across all handlers
    - Send duplicate enrollment event → Verify no duplicate member
    - Send duplicate purchase event → Verify balance not double-credited
    - Send duplicate redemption event → Verify balance not double-debited
    - _Requirements: 10.1-10.4_

  - [ ]* 13.5 Test error handling and DLQ behavior
    - Send invalid events → Verify errors returned
    - Send events causing permanent failures → Verify DLQ receives messages
    - Test retry logic for transient errors
    - _Requirements: 9.1-9.5_

- [x] 14. Create CDK deployment configuration and documentation
  - [x] 14.1 Configure CDK deployment settings
    - Set up environment-specific configuration (dev, staging, prod)
    - Configure stack tags and naming conventions
    - Set removal policies (RETAIN for prod, DESTROY for dev)
    - Configure CDK context values
    - Create deployment scripts
    - _Requirements: All (deployment)_

  - [x] 14.2 Write deployment and operations documentation
    - Document deployment process and prerequisites
    - Document environment variables and configuration
    - Document monitoring and alarm response procedures
    - Document DLQ message handling procedures
    - Create runbook for common operational tasks
    - _Requirements: All (operations)_

- [x] 15. Final checkpoint - Complete system validation
  - Run all unit tests and property tests
  - Run all integration tests
  - Deploy to test environment and run smoke tests
  - Verify all CloudWatch alarms configured correctly
  - Verify API endpoints respond correctly
  - Verify scheduled handlers execute on schedule
  - Ensure all tests pass, ask the user if questions arise

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP delivery
- Each task references specific requirements for traceability
- Property tests validate universal correctness properties from the design document
- Unit tests validate specific examples, edge cases, and error conditions
- Integration tests validate end-to-end flows across multiple components
- Checkpoints ensure incremental validation and provide opportunities for user feedback
- All Lambda functions use Python 3.11+ with type hints
- All infrastructure code uses TypeScript CDK with strict mode
- DynamoDB conditional updates prevent race conditions
- Idempotency ensures safe duplicate event handling
- DLQs capture failed events for manual review
- CloudWatch alarms provide operational visibility
