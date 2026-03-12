import * as cdk from 'aws-cdk-lib/core';
import { Template, Match } from 'aws-cdk-lib/assertions';
import * as Rewards from '../lib/rewards-stack';
import { EnvironmentConfig, NamingConventions } from '../lib/environment-config';

// Test configuration
const testEnvConfig: EnvironmentConfig = {
  account: '123456789012',
  region: 'us-east-1',
  removalPolicy: 'DESTROY',
  logRetention: 7,
  enableDetailedMonitoring: false,
  enableXRayTracing: true,
  apiThrottling: {
    rateLimit: 100,
    burstLimit: 200
  },
  lambdaMemory: {
    query: 256,
    enrollment: 256,
    purchase: 256,
    redemption: 256,
    tierEvaluation: 512,
    expiration: 512
  }
};

const testNamingConventions: NamingConventions = {
  stackName: 'rewards-test',
  resourcePrefix: 'rewards-test',
  tableName: 'rewards-program-test',
  eventBusName: 'rewards-program-events-test',
  apiName: 'rewards-program-api-test'
};

describe('RewardsStack DynamoDB Table', () => {
  let template: Template;

  beforeAll(() => {
    const app = new cdk.App();
    const stack = new Rewards.RewardsStack(app, 'TestStack', {
      environment: 'test',
      envConfig: testEnvConfig,
      namingConventions: testNamingConventions
    });
    template = Template.fromStack(stack);
  });

  test('DynamoDB table is created with correct configuration', () => {
    template.hasResourceProperties('AWS::DynamoDB::Table', {
      TableName: 'rewards-program-test',
      BillingMode: 'PAY_PER_REQUEST',
      PointInTimeRecoverySpecification: {
        PointInTimeRecoveryEnabled: true,
      },
      SSESpecification: {
        SSEEnabled: true,
        SSEType: 'KMS',
      },
    });
  });

  test('DynamoDB table has correct primary key schema', () => {
    template.hasResourceProperties('AWS::DynamoDB::Table', {
      KeySchema: [
        {
          AttributeName: 'PK',
          KeyType: 'HASH',
        },
        {
          AttributeName: 'SK',
          KeyType: 'RANGE',
        },
      ],
      AttributeDefinitions: Match.arrayWith([
        {
          AttributeName: 'PK',
          AttributeType: 'S',
        },
        {
          AttributeName: 'SK',
          AttributeType: 'S',
        },
      ]),
    });
  });

  test('DynamoDB table has GSI1 for tier-based queries', () => {
    template.hasResourceProperties('AWS::DynamoDB::Table', {
      GlobalSecondaryIndexes: Match.arrayWith([
        Match.objectLike({
          IndexName: 'GSI1',
          KeySchema: [
            {
              AttributeName: 'GSI1PK',
              KeyType: 'HASH',
            },
            {
              AttributeName: 'GSI1SK',
              KeyType: 'RANGE',
            },
          ],
          Projection: {
            ProjectionType: 'ALL',
          },
        }),
      ]),
    });
  });

  test('DynamoDB table has GSI2 for transaction idempotency lookups', () => {
    template.hasResourceProperties('AWS::DynamoDB::Table', {
      GlobalSecondaryIndexes: Match.arrayWith([
        Match.objectLike({
          IndexName: 'GSI2',
          KeySchema: [
            {
              AttributeName: 'GSI2PK',
              KeyType: 'HASH',
            },
            {
              AttributeName: 'GSI2SK',
              KeyType: 'RANGE',
            },
          ],
          Projection: {
            ProjectionType: 'ALL',
          },
        }),
      ]),
    });
  });

  test('DynamoDB table has correct attribute definitions for GSIs', () => {
    template.hasResourceProperties('AWS::DynamoDB::Table', {
      AttributeDefinitions: Match.arrayWith([
        {
          AttributeName: 'GSI1PK',
          AttributeType: 'S',
        },
        {
          AttributeName: 'GSI1SK',
          AttributeType: 'S',
        },
        {
          AttributeName: 'GSI2PK',
          AttributeType: 'S',
        },
        {
          AttributeName: 'GSI2SK',
          AttributeType: 'S',
        },
      ]),
    });
  });

  test('DynamoDB table has correct resource tags', () => {
    const resources = template.findResources('AWS::DynamoDB::Table');
    const tableResource = Object.values(resources)[0] as any;
    const tags = tableResource.Properties.Tags;
    
    expect(tags).toEqual(
      expect.arrayContaining([
        expect.objectContaining({ Key: 'service', Value: 'rewards-program' }),
        expect.objectContaining({ Key: 'cost-center', Value: 'customer-loyalty' }),
        expect.objectContaining({ Key: 'environment', Value: 'dev' }),
      ])
    );
  });

  test('KMS key is created for table encryption', () => {
    template.hasResourceProperties('AWS::KMS::Key', {
      Description: 'KMS key for rewards program DynamoDB table encryption',
      EnableKeyRotation: true,
    });
  });

  test('DynamoDB table has RETAIN removal policy', () => {
    template.hasResource('AWS::DynamoDB::Table', {
      DeletionPolicy: 'Retain',
      UpdateReplacePolicy: 'Retain',
    });
  });

  test('Stack outputs table name and ARN', () => {
    template.hasOutput('RewardsTableName', {
      Description: 'DynamoDB table name for rewards program',
      Export: {
        Name: 'RewardsTableName',
      },
    });

    template.hasOutput('RewardsTableArn', {
      Description: 'DynamoDB table ARN for rewards program',
      Export: {
        Name: 'RewardsTableArn',
      },
    });
  });
});

describe('RewardsStack EventBridge Infrastructure', () => {
  let template: Template;

  beforeAll(() => {
    const app = new cdk.App();
    const stack = new Rewards.RewardsStack(app, 'TestStackEventBridge', {
      environment: 'test',
      envConfig: testEnvConfig,
      namingConventions: testNamingConventions
    });
    template = Template.fromStack(stack);
  });

  test('EventBridge custom event bus is created', () => {
    template.hasResourceProperties('AWS::Events::EventBus', {
      Name: 'rewards-program-events',
    });
  });

  test('Event bus has correct resource tags', () => {
    const resources = template.findResources('AWS::Events::EventBus');
    const eventBusResource = Object.values(resources)[0] as any;
    const tags = eventBusResource.Properties.Tags;
    
    expect(tags).toEqual(
      expect.arrayContaining([
        expect.objectContaining({ Key: 'service', Value: 'rewards-program' }),
        expect.objectContaining({ Key: 'cost-center', Value: 'customer-loyalty' }),
        expect.objectContaining({ Key: 'environment', Value: 'dev' }),
      ])
    );
  });

  test('Signup event rule is created with correct pattern', () => {
    template.hasResourceProperties('AWS::Events::Rule', {
      Name: 'rewards-signup-events',
      Description: 'Routes member signup events to enrollment handler',
      EventPattern: {
        source: ['rewards.program'],
        'detail-type': ['rewards.member.signup'],
      },
    });
  });

  test('Purchase event rule is created with correct pattern', () => {
    template.hasResourceProperties('AWS::Events::Rule', {
      Name: 'rewards-purchase-events',
      Description: 'Routes purchase transaction events to purchase handler',
      EventPattern: {
        source: ['rewards.program'],
        'detail-type': ['rewards.transaction.purchase'],
      },
    });
  });

  test('Redemption event rule is created with correct pattern', () => {
    template.hasResourceProperties('AWS::Events::Rule', {
      Name: 'rewards-redemption-events',
      Description: 'Routes redemption transaction events to redemption handler',
      EventPattern: {
        source: ['rewards.program'],
        'detail-type': ['rewards.transaction.redemption'],
      },
    });
  });

  test('Tier evaluation scheduled rule is created for daily 00:00 UTC', () => {
    template.hasResourceProperties('AWS::Events::Rule', {
      Name: 'rewards-tier-evaluation-schedule',
      Description: 'Triggers tier evaluation handler daily at 00:00 UTC',
      ScheduleExpression: 'cron(0 0 * * ? *)',
    });
  });

  test('Expiration scheduled rule is created for daily 01:00 UTC', () => {
    template.hasResourceProperties('AWS::Events::Rule', {
      Name: 'rewards-expiration-schedule',
      Description: 'Triggers star expiration handler daily at 01:00 UTC',
      ScheduleExpression: 'cron(0 1 * * ? *)',
    });
  });

  test('Stack outputs event bus name and ARN', () => {
    template.hasOutput('RewardsEventBusName', {
      Description: 'EventBridge event bus name for rewards program',
      Export: {
        Name: 'RewardsEventBusName',
      },
    });

    template.hasOutput('RewardsEventBusArn', {
      Description: 'EventBridge event bus ARN for rewards program',
      Export: {
        Name: 'RewardsEventBusArn',
      },
    });
  });

  test('All event rules reference the custom event bus', () => {
    const rules = template.findResources('AWS::Events::Rule', {
      Properties: {
        EventPattern: Match.anyValue(),
      },
    });

    // Count event-pattern rules (not scheduled rules)
    const eventPatternRules = Object.values(rules).filter((rule: any) => 
      rule.Properties.EventPattern !== undefined
    );

    expect(eventPatternRules.length).toBe(3); // signup, purchase, redemption

    // Verify each event-pattern rule references the event bus
    eventPatternRules.forEach((rule: any) => {
      expect(rule.Properties.EventBusName).toBeDefined();
    });
  });
});

describe('RewardsStack API Gateway Infrastructure', () => {
  let template: Template;

  beforeAll(() => {
    const app = new cdk.App();
    const stack = new Rewards.RewardsStack(app, 'TestStackApiGateway', {
      environment: 'test',
      envConfig: testEnvConfig,
      namingConventions: testNamingConventions
    });
    template = Template.fromStack(stack);
  });

  test('REST API is created with correct configuration', () => {
    template.hasResourceProperties('AWS::ApiGateway::RestApi', {
      Name: 'rewards-program-api',
      Description: 'REST API for querying member balances and transaction history',
      EndpointConfiguration: {
        Types: ['REGIONAL'],
      },
    });
  });

  test('API Gateway has correct resource tags', () => {
    const resources = template.findResources('AWS::ApiGateway::RestApi');
    const apiResource = Object.values(resources)[0] as any;
    const tags = apiResource.Properties.Tags;
    
    expect(tags).toEqual(
      expect.arrayContaining([
        expect.objectContaining({ Key: 'service', Value: 'rewards-program' }),
        expect.objectContaining({ Key: 'cost-center', Value: 'customer-loyalty' }),
        expect.objectContaining({ Key: 'environment', Value: 'dev' }),
      ])
    );
  });

  test('API Gateway deployment is created with v1 stage', () => {
    template.hasResourceProperties('AWS::ApiGateway::Stage', {
      StageName: 'v1',
    });
  });

  test('API Gateway stage has throttling configured', () => {
    template.hasResourceProperties('AWS::ApiGateway::Stage', {
      MethodSettings: Match.arrayWith([
        Match.objectLike({
          ThrottlingRateLimit: 1000,
          ThrottlingBurstLimit: 2000,
        }),
      ]),
    });
  });

  test('API Gateway stage has logging enabled', () => {
    template.hasResourceProperties('AWS::ApiGateway::Stage', {
      MethodSettings: Match.arrayWith([
        Match.objectLike({
          LoggingLevel: 'INFO',
          DataTraceEnabled: true,
        }),
      ]),
    });
  });

  test('CloudWatch log group is created for API access logs', () => {
    template.hasResourceProperties('AWS::Logs::LogGroup', {
      LogGroupName: '/aws/apigateway/rewards-program',
      RetentionInDays: 30,
    });
  });

  test('API Gateway stage has access logging configured', () => {
    template.hasResourceProperties('AWS::ApiGateway::Stage', {
      AccessLogSetting: Match.objectLike({
        DestinationArn: Match.anyValue(),
        Format: Match.stringLikeRegexp('.*requestTime.*status.*'),
      }),
    });
  });

  test('CORS is configured with correct settings', () => {
    // Check for OPTIONS method on members resource
    const methods = template.findResources('AWS::ApiGateway::Method', {
      Properties: {
        HttpMethod: 'OPTIONS',
      },
    });

    expect(Object.keys(methods).length).toBeGreaterThan(0);

    // Verify CORS headers in method responses
    Object.values(methods).forEach((method: any) => {
      const responseParameters = method.Properties.Integration?.IntegrationResponses?.[0]?.ResponseParameters;
      if (responseParameters) {
        expect(responseParameters).toMatchObject(
          expect.objectContaining({
            'method.response.header.Access-Control-Allow-Headers': expect.any(String),
            'method.response.header.Access-Control-Allow-Methods': expect.any(String),
            'method.response.header.Access-Control-Allow-Origin': expect.any(String),
          })
        );
      }
    });
  });

  test('Request validator is created for query parameters', () => {
    template.hasResourceProperties('AWS::ApiGateway::RequestValidator', {
      Name: 'rewards-query-validator',
      ValidateRequestParameters: true,
      ValidateRequestBody: false,
    });
  });

  test('Members resource is created at /members', () => {
    const resources = template.findResources('AWS::ApiGateway::Resource', {
      Properties: {
        PathPart: 'members',
      },
    });

    expect(Object.keys(resources).length).toBe(1);
  });

  test('Member by ID resource is created at /members/{membershipId}', () => {
    const resources = template.findResources('AWS::ApiGateway::Resource', {
      Properties: {
        PathPart: '{membershipId}',
      },
    });

    expect(Object.keys(resources).length).toBe(1);
  });

  test('Transactions resource is created at /members/{membershipId}/transactions', () => {
    const resources = template.findResources('AWS::ApiGateway::Resource', {
      Properties: {
        PathPart: 'transactions',
      },
    });

    expect(Object.keys(resources).length).toBe(1);
  });

  test('Usage plan is created with correct throttling and quota', () => {
    template.hasResourceProperties('AWS::ApiGateway::UsagePlan', {
      UsagePlanName: 'rewards-standard-plan',
      Description: 'Standard usage plan for rewards API',
      Throttle: {
        RateLimit: 1000,
        BurstLimit: 2000,
      },
      Quota: {
        Limit: 100000,
        Period: 'DAY',
      },
    });
  });

  test('Usage plan is associated with API stage', () => {
    template.hasResourceProperties('AWS::ApiGateway::UsagePlan', {
      ApiStages: Match.arrayWith([
        Match.objectLike({
          ApiId: Match.anyValue(),
          Stage: Match.anyValue(),
        }),
      ]),
    });
  });

  test('Stack outputs API Gateway URL and ID', () => {
    template.hasOutput('RewardsApiUrl', {
      Description: 'REST API Gateway URL for rewards program',
      Export: {
        Name: 'RewardsApiUrl',
      },
    });

    template.hasOutput('RewardsApiId', {
      Description: 'REST API Gateway ID for rewards program',
      Export: {
        Name: 'RewardsApiId',
      },
    });
  });

  test('API Gateway has CloudWatch role enabled', () => {
    // CDK creates an account-level CloudWatch role for API Gateway
    const accounts = template.findResources('AWS::ApiGateway::Account');
    expect(Object.keys(accounts).length).toBeGreaterThan(0);
  });
});

describe('RewardsStack Enrollment Lambda Infrastructure', () => {
  let template: Template;

  beforeAll(() => {
    const app = new cdk.App();
    const stack = new Rewards.RewardsStack(app, 'TestStackEnrollment', {
      environment: 'test',
      envConfig: testEnvConfig,
      namingConventions: testNamingConventions
    });
    template = Template.fromStack(stack);
  });

  test('Enrollment Lambda function is created with correct configuration', () => {
    template.hasResourceProperties('AWS::Lambda::Function', {
      FunctionName: 'rewards-enrollment-handler',
      Description: 'Processes member enrollment events from EventBridge',
      Runtime: 'python3.11',
      Handler: 'enrollment.handler.handler',
      MemorySize: 512,
      Timeout: 30,
      TracingConfig: {
        Mode: 'Active',
      },
    });
  });

  test('Enrollment Lambda has correct environment variables', () => {
    template.hasResourceProperties('AWS::Lambda::Function', {
      FunctionName: 'rewards-enrollment-handler',
      Environment: {
        Variables: {
          TABLE_NAME: Match.anyValue(),
          POWERTOOLS_SERVICE_NAME: 'enrollment',
          LOG_LEVEL: 'INFO',
        },
      },
    });
  });

  test('Enrollment Lambda has correct resource tags', () => {
    const functions = template.findResources('AWS::Lambda::Function', {
      Properties: {
        FunctionName: 'rewards-enrollment-handler',
      },
    });
    
    const lambdaResource = Object.values(functions)[0] as any;
    const tags = lambdaResource.Properties.Tags;
    
    expect(tags).toEqual(
      expect.arrayContaining([
        expect.objectContaining({ Key: 'service', Value: 'rewards-program' }),
        expect.objectContaining({ Key: 'cost-center', Value: 'customer-loyalty' }),
        expect.objectContaining({ Key: 'environment', Value: 'dev' }),
      ])
    );
  });

  test('Enrollment Lambda has DLQ configured', () => {
    template.hasResourceProperties('AWS::Lambda::Function', {
      FunctionName: 'rewards-enrollment-handler',
      DeadLetterConfig: {
        TargetArn: Match.anyValue(),
      },
    });
  });

  test('Enrollment DLQ is created with correct configuration', () => {
    template.hasResourceProperties('AWS::SQS::Queue', {
      QueueName: 'rewards-enrollment-dlq',
      MessageRetentionPeriod: 1209600, // 14 days in seconds
      KmsMasterKeyId: 'alias/aws/sqs',
    });
  });

  test('Enrollment Lambda has retry attempts configured', () => {
    template.hasResourceProperties('AWS::Lambda::EventInvokeConfig', {
      MaximumRetryAttempts: 2,
    });
  });

  test('Enrollment Lambda has log retention configured', () => {
    template.hasResourceProperties('AWS::Logs::LogGroup', {
      LogGroupName: '/aws/lambda/rewards-enrollment-handler',
      RetentionInDays: 30,
    });
  });

  test('Enrollment Lambda has DynamoDB write permissions', () => {
    template.hasResourceProperties('AWS::IAM::Policy', {
      PolicyDocument: {
        Statement: Match.arrayWith([
          Match.objectLike({
            Action: Match.arrayWith([
              'dynamodb:BatchWriteItem',
              'dynamodb:PutItem',
              'dynamodb:UpdateItem',
              'dynamodb:DeleteItem',
            ]),
            Effect: 'Allow',
          }),
        ]),
      },
    });
  });

  test('Enrollment Lambda has X-Ray tracing permissions', () => {
    template.hasResourceProperties('AWS::IAM::Policy', {
      PolicyDocument: {
        Statement: Match.arrayWith([
          Match.objectLike({
            Action: Match.arrayWith([
              'xray:PutTraceSegments',
              'xray:PutTelemetryRecords',
            ]),
            Effect: 'Allow',
          }),
        ]),
      },
    });
  });

  test('Signup event rule targets enrollment Lambda', () => {
    const rules = template.findResources('AWS::Events::Rule', {
      Properties: {
        Name: 'rewards-signup-events',
      },
    });

    const signupRule = Object.values(rules)[0] as any;
    expect(signupRule.Properties.Targets).toBeDefined();
    expect(signupRule.Properties.Targets.length).toBeGreaterThan(0);
    
    const target = signupRule.Properties.Targets[0];
    expect(target.Arn).toBeDefined();
    expect(target.RetryPolicy).toEqual({
      MaximumRetryAttempts: 2,
      MaximumEventAgeInSeconds: 7200, // 2 hours in seconds
    });
    expect(target.DeadLetterConfig).toBeDefined();
  });

  test('CloudWatch alarm is created for enrollment DLQ', () => {
    template.hasResourceProperties('AWS::CloudWatch::Alarm', {
      AlarmName: 'rewards-enrollment-dlq-messages',
      AlarmDescription: 'Alert when enrollment DLQ receives messages',
      ComparisonOperator: 'GreaterThanOrEqualToThreshold',
      EvaluationPeriods: 1,
      Threshold: 1,
      TreatMissingData: 'notBreaching',
    });
  });

  test('SNS topic is created for alarms', () => {
    template.hasResourceProperties('AWS::SNS::Topic', {
      TopicName: 'rewards-program-alarms',
      DisplayName: 'Rewards Program Alarms',
    });
  });

  test('DLQ alarm has SNS action configured', () => {
    const alarms = template.findResources('AWS::CloudWatch::Alarm', {
      Properties: {
        AlarmName: 'rewards-enrollment-dlq-messages',
      },
    });

    const alarm = Object.values(alarms)[0] as any;
    expect(alarm.Properties.AlarmActions).toBeDefined();
    expect(alarm.Properties.AlarmActions.length).toBeGreaterThan(0);
  });

  test('Enrollment Lambda has permission to be invoked by EventBridge', () => {
    template.hasResourceProperties('AWS::Lambda::Permission', {
      Action: 'lambda:InvokeFunction',
      Principal: 'events.amazonaws.com',
    });
  });
});
