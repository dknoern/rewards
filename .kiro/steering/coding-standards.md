---
inclusion: always
---

# Coding Standards

## Python Standards

- Use Python 3.11+ features and type hints throughout
- Follow PEP 8 style guide with line length of 100 characters
- Use `black` for formatting and `ruff` for linting
- Prefer dataclasses or Pydantic models for data structures
- Use descriptive variable names; avoid single-letter variables except in comprehensions
- Write docstrings for all public functions, classes, and modules (Google style)
- Use f-strings for string formatting
- Prefer explicit over implicit; avoid magic numbers and strings
- Use context managers (`with` statements) for resource management
- Handle exceptions specifically; avoid bare `except` clauses

## TypeScript Standards (CDK)

- Use TypeScript for all CDK infrastructure code
- Enable strict mode in tsconfig.json
- Use explicit types; avoid `any` type
- Prefer interfaces over type aliases for object shapes
- Use const assertions for immutable values
- Follow consistent naming: PascalCase for classes, camelCase for variables/functions
- Use async/await over raw promises
- Organize imports: external libraries first, then internal modules

## AWS CDK Standards

- Use CDK v2 with TypeScript
- One stack per logical service boundary
- Use constructs to encapsulate reusable infrastructure patterns
- Tag all resources with environment, service, and cost-center
- Use `RemovalPolicy.RETAIN` for stateful resources in production
- Externalize configuration using environment variables or SSM parameters
- Use CDK context for environment-specific values
- Prefer L2/L3 constructs over L1 (Cfn) constructs when available
- Name resources with consistent patterns: `{service}-{resource}-{env}`

## Code Organization

- Use dependency injection for better testability
- Keep functions small and focused (single responsibility)
- Separate business logic from infrastructure/framework code
- Use repository pattern for data access
- Organize by feature/domain, not by technical layer
- Keep configuration separate from code
