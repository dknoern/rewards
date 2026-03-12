---
inclusion: always
---

# Architecture Guidelines

## Event-Driven Architecture

- Use Amazon EventBridge as the primary event bus
- Design events as immutable facts about what happened
- Use past-tense naming for events (e.g., `OrderPlaced`, `PaymentProcessed`)
- Include event metadata: timestamp, version, correlation ID, source
- Keep events small and focused; avoid large payloads
- Use dead-letter queues (DLQ) for failed event processing
- Implement idempotency for all event handlers
- Use SQS for reliable async processing with retry logic

## RESTful API Design

- Use API Gateway with Lambda integration
- Follow REST conventions: GET, POST, PUT, PATCH, DELETE
- Use plural nouns for resource endpoints (`/orders`, `/users`)
- Version APIs in the URL path (`/v1/orders`)
- Return appropriate HTTP status codes (200, 201, 400, 404, 500)
- Use JSON for request/response bodies
- Implement pagination for list endpoints (limit/offset or cursor-based)
- Include HATEOAS links where appropriate
- Use request validation at the API Gateway level
- Implement rate limiting and throttling

## Service Architecture

- Design loosely coupled, independently deployable services
- Each service owns its data; no shared databases
- Use async communication between services via events
- Implement circuit breakers for external dependencies
- Use Lambda for compute; prefer single-purpose functions
- Store state in DynamoDB, RDS, or S3 as appropriate
- Use Step Functions for complex workflows and orchestration
- Implement saga pattern for distributed transactions
- Use API Gateway for synchronous service-to-service calls when needed

## Data Management

- Use DynamoDB for high-scale, low-latency access patterns
- Design single-table DynamoDB schemas where appropriate
- Use RDS Aurora Serverless for relational data needs
- Store large objects and files in S3
- Implement data versioning and audit trails
- Use DynamoDB Streams or EventBridge for change data capture
- Encrypt data at rest and in transit
