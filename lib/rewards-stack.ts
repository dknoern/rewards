import * as cdk from 'aws-cdk-lib/core';
import * as dynamodb from 'aws-cdk-lib/aws-dynamodb';
import * as kms from 'aws-cdk-lib/aws-kms';
import * as events from 'aws-cdk-lib/aws-events';
import * as targets from 'aws-cdk-lib/aws-events-targets';
import * as lambda from 'aws-cdk-lib/aws-lambda';
import * as sqs from 'aws-cdk-lib/aws-sqs';
import * as cloudwatch from 'aws-cdk-lib/aws-cloudwatch';
import * as cloudwatch_actions from 'aws-cdk-lib/aws-cloudwatch-actions';
import * as sns from 'aws-cdk-lib/aws-sns';
import * as apigateway from 'aws-cdk-lib/aws-apigateway';
import * as logs from 'aws-cdk-lib/aws-logs';
import { Tags } from 'aws-cdk-lib/core';
import { Construct } from 'constructs';
import { RewardsStackProps } from './environment-config';

export class RewardsStack extends cdk.Stack {
  public readonly rewardsTable: dynamodb.Table;
  public readonly rewardsEventBus: events.EventBus;
  public readonly rewardsApi: apigateway.RestApi;

  constructor(scope: Construct, id: string, props: RewardsStackProps) {
    super(scope, id, props);

    const { environment, envConfig, namingConventions } = props;

    // Helper function to replace environment placeholder in names
    const resolveName = (template: string): string => {
      return template.replace('${environment}', environment);
    };

    // Determine removal policy based on environment
    const removalPolicy = envConfig.removalPolicy === 'RETAIN' 
      ? cdk.RemovalPolicy.RETAIN 
      : cdk.RemovalPolicy.DESTROY;

    // Determine log retention based on environment
    const logRetention = envConfig.logRetention === 7 
      ? logs.RetentionDays.ONE_WEEK
      : envConfig.logRetention === 30 
      ? logs.RetentionDays.ONE_MONTH
      : logs.RetentionDays.THREE_MONTHS;

    // KMS key for DynamoDB encryption
    const tableEncryptionKey = new kms.Key(this, 'RewardsTableKey', {
      description: `KMS key for rewards program DynamoDB table encryption - ${environment}`,
      enableKeyRotation: true,
      removalPolicy: removalPolicy,
    });

    // DynamoDB table with single-table design
    this.rewardsTable = new dynamodb.Table(this, 'RewardsTable', {
      tableName: resolveName(namingConventions.tableName || 'rewards-program-${environment}'),
      partitionKey: {
        name: 'PK',
        type: dynamodb.AttributeType.STRING,
      },
      sortKey: {
        name: 'SK',
        type: dynamodb.AttributeType.STRING,
      },
      billingMode: dynamodb.BillingMode.PAY_PER_REQUEST,
      encryption: dynamodb.TableEncryption.CUSTOMER_MANAGED,
      encryptionKey: tableEncryptionKey,
      pointInTimeRecoverySpecification: {
        pointInTimeRecoveryEnabled: true,
      },
      timeToLiveAttribute: 'ttl',
      removalPolicy: removalPolicy,
    });

    // Add resource tags
    Tags.of(this.rewardsTable).add('environment', environment);
    Tags.of(this.rewardsTable).add('service', 'rewards-program');
    Tags.of(this.rewardsTable).add('cost-center', 'customer-loyalty');

    // GSI1: For querying by tier and evaluation date
    this.rewardsTable.addGlobalSecondaryIndex({
      indexName: 'GSI1',
      partitionKey: {
        name: 'GSI1PK',
        type: dynamodb.AttributeType.STRING,
      },
      sortKey: {
        name: 'GSI1SK',
        type: dynamodb.AttributeType.STRING,
      },
      projectionType: dynamodb.ProjectionType.ALL,
    });

    // GSI2: For transaction idempotency lookups
    this.rewardsTable.addGlobalSecondaryIndex({
      indexName: 'GSI2',
      partitionKey: {
        name: 'GSI2PK',
        type: dynamodb.AttributeType.STRING,
      },
      sortKey: {
        name: 'GSI2SK',
        type: dynamodb.AttributeType.STRING,
      },
      projectionType: dynamodb.ProjectionType.ALL,
    });

    // Custom EventBridge event bus for rewards events
    this.rewardsEventBus = new events.EventBus(this, 'RewardsEventBus', {
      eventBusName: resolveName(namingConventions.eventBusName || 'rewards-program-events-${environment}'),
    });

    // Add resource tags to event bus
    Tags.of(this.rewardsEventBus).add('environment', environment);
    Tags.of(this.rewardsEventBus).add('service', 'rewards-program');
    Tags.of(this.rewardsEventBus).add('cost-center', 'customer-loyalty');

    // Event rule for signup events
    const signupRule = new events.Rule(this, 'SignupEventRule', {
      eventBus: this.rewardsEventBus,
      ruleName: `rewards-signup-events-${environment}`,
      description: 'Routes member signup events to enrollment handler',
      eventPattern: {
        source: ['rewards.program'],
        detailType: ['rewards.member.signup'],
      },
    });

    // Dead Letter Queue for enrollment Lambda
    const enrollmentDLQ = new sqs.Queue(this, 'EnrollmentDLQ', {
      queueName: `rewards-enrollment-dlq-${environment}`,
      retentionPeriod: cdk.Duration.days(14),
      encryption: sqs.QueueEncryption.KMS_MANAGED,
    });

    // SNS topic for DLQ alarms
    const alarmTopic = new sns.Topic(this, 'RewardsAlarmTopic', {
      topicName: `rewards-program-alarms-${environment}`,
      displayName: `Rewards Program Alarms - ${environment.toUpperCase()}`,
    });

    // CloudWatch alarm for enrollment DLQ
    const enrollmentDLQAlarm = new cloudwatch.Alarm(this, 'EnrollmentDLQAlarm', {
      alarmName: `rewards-enrollment-dlq-messages-${environment}`,
      alarmDescription: 'Alert when enrollment DLQ receives messages',
      metric: enrollmentDLQ.metricApproximateNumberOfMessagesVisible(),
      threshold: 1,
      evaluationPeriods: 1,
      comparisonOperator: cloudwatch.ComparisonOperator.GREATER_THAN_OR_EQUAL_TO_THRESHOLD,
      treatMissingData: cloudwatch.TreatMissingData.NOT_BREACHING,
    });

    enrollmentDLQAlarm.addAlarmAction(new cloudwatch_actions.SnsAction(alarmTopic));

    // CloudWatch log group for enrollment Lambda
    const enrollmentLogGroup = new logs.LogGroup(this, 'EnrollmentLogGroup', {
      logGroupName: `/aws/lambda/rewards-enrollment-handler-${environment}`,
      retention: logRetention,
      removalPolicy: cdk.RemovalPolicy.DESTROY,
    });

    // Enrollment Lambda function
    const enrollmentLambda = new lambda.Function(this, 'EnrollmentHandler', {
      functionName: `rewards-enrollment-handler-${environment}`,
      description: 'Processes member enrollment events from EventBridge',
      runtime: lambda.Runtime.PYTHON_3_11,
      handler: 'enrollment.handler.handler',
      code: lambda.Code.fromAsset('lambda'),
      memorySize: envConfig.lambdaMemory.enrollment,
      timeout: cdk.Duration.seconds(30),
      environment: {
        TABLE_NAME: this.rewardsTable.tableName,
        POWERTOOLS_SERVICE_NAME: 'enrollment',
        LOG_LEVEL: 'INFO',
        ENVIRONMENT: environment,
      },
      tracing: envConfig.enableXRayTracing ? lambda.Tracing.ACTIVE : lambda.Tracing.DISABLED,
      deadLetterQueue: enrollmentDLQ,
      retryAttempts: 2,
      logGroup: enrollmentLogGroup,
    });

    // Grant DynamoDB read/write permissions to enrollment Lambda
    this.rewardsTable.grantReadWriteData(enrollmentLambda);

    // Add resource tags
    Tags.of(enrollmentLambda).add('environment', environment);
    Tags.of(enrollmentLambda).add('service', 'rewards-program');
    Tags.of(enrollmentLambda).add('cost-center', 'customer-loyalty');

    // Connect signup rule to enrollment Lambda
    signupRule.addTarget(new targets.LambdaFunction(enrollmentLambda, {
      deadLetterQueue: enrollmentDLQ,
      maxEventAge: cdk.Duration.hours(2),
      retryAttempts: 2,
    }));

    // Event rule for purchase events
    const purchaseRule = new events.Rule(this, 'PurchaseEventRule', {
      eventBus: this.rewardsEventBus,
      ruleName: `rewards-purchase-events-${environment}`,
      description: 'Routes purchase transaction events to purchase handler',
      eventPattern: {
        source: ['rewards.program'],
        detailType: ['rewards.transaction.purchase'],
      },
    });
    // Dead Letter Queue for purchase Lambda
    const purchaseDLQ = new sqs.Queue(this, 'PurchaseDLQ', {
      queueName: `rewards-purchase-dlq-${environment}`,
      retentionPeriod: cdk.Duration.days(14),
      encryption: sqs.QueueEncryption.KMS_MANAGED,
    });

    // CloudWatch alarm for purchase DLQ
    const purchaseDLQAlarm = new cloudwatch.Alarm(this, 'PurchaseDLQAlarm', {
      alarmName: `rewards-purchase-dlq-messages-${environment}`,
      alarmDescription: 'Alert when purchase DLQ receives messages',
      metric: purchaseDLQ.metricApproximateNumberOfMessagesVisible(),
      threshold: 1,
      evaluationPeriods: 1,
      comparisonOperator: cloudwatch.ComparisonOperator.GREATER_THAN_OR_EQUAL_TO_THRESHOLD,
      treatMissingData: cloudwatch.TreatMissingData.NOT_BREACHING,
    });

    purchaseDLQAlarm.addAlarmAction(new cloudwatch_actions.SnsAction(alarmTopic));

    // CloudWatch log group for purchase Lambda
    const purchaseLogGroup = new logs.LogGroup(this, 'PurchaseLogGroup', {
      logGroupName: `/aws/lambda/rewards-purchase-handler-${environment}`,
      retention: logRetention,
      removalPolicy: cdk.RemovalPolicy.DESTROY,
    });

    // Purchase Lambda function
    const purchaseLambda = new lambda.Function(this, 'PurchaseHandler', {
      functionName: `rewards-purchase-handler-${environment}`,
      description: 'Processes purchase transaction events from EventBridge',
      runtime: lambda.Runtime.PYTHON_3_11,
      handler: 'purchase.handler.handler',
      code: lambda.Code.fromAsset('lambda'),
      memorySize: envConfig.lambdaMemory.purchase,
      timeout: cdk.Duration.seconds(30),
      environment: {
        TABLE_NAME: this.rewardsTable.tableName,
        POWERTOOLS_SERVICE_NAME: 'purchase',
        LOG_LEVEL: 'INFO',
        ENVIRONMENT: environment,
      },
      tracing: envConfig.enableXRayTracing ? lambda.Tracing.ACTIVE : lambda.Tracing.DISABLED,
      deadLetterQueue: purchaseDLQ,
      retryAttempts: 2,
      logGroup: purchaseLogGroup,
    });

    // Grant DynamoDB read/write permissions to purchase Lambda
    this.rewardsTable.grantReadWriteData(purchaseLambda);

    // Add resource tags
    Tags.of(purchaseLambda).add('environment', environment);
    Tags.of(purchaseLambda).add('service', 'rewards-program');
    Tags.of(purchaseLambda).add('cost-center', 'customer-loyalty');

    // Connect purchase rule to purchase Lambda
    purchaseRule.addTarget(new targets.LambdaFunction(purchaseLambda, {
      deadLetterQueue: purchaseDLQ,
      maxEventAge: cdk.Duration.hours(2),
      retryAttempts: 2,
    }));

    // Event rule for redemption events
    const redemptionRule = new events.Rule(this, 'RedemptionEventRule', {
      eventBus: this.rewardsEventBus,
      ruleName: `rewards-redemption-events-${environment}`,
      description: 'Routes redemption transaction events to redemption handler',
      eventPattern: {
        source: ['rewards.program'],
        detailType: ['rewards.transaction.redemption'],
      },
    });
    // Dead Letter Queue for redemption Lambda
    const redemptionDLQ = new sqs.Queue(this, 'RedemptionDLQ', {
      queueName: `rewards-redemption-dlq-${environment}`,
      retentionPeriod: cdk.Duration.days(14),
      encryption: sqs.QueueEncryption.KMS_MANAGED,
    });

    // CloudWatch alarm for redemption DLQ
    const redemptionDLQAlarm = new cloudwatch.Alarm(this, 'RedemptionDLQAlarm', {
      alarmName: `rewards-redemption-dlq-messages-${environment}`,
      alarmDescription: 'Alert when redemption DLQ receives messages',
      metric: redemptionDLQ.metricApproximateNumberOfMessagesVisible(),
      threshold: 1,
      evaluationPeriods: 1,
      comparisonOperator: cloudwatch.ComparisonOperator.GREATER_THAN_OR_EQUAL_TO_THRESHOLD,
      treatMissingData: cloudwatch.TreatMissingData.NOT_BREACHING,
    });

    redemptionDLQAlarm.addAlarmAction(new cloudwatch_actions.SnsAction(alarmTopic));

    // CloudWatch log group for redemption Lambda
    const redemptionLogGroup = new logs.LogGroup(this, 'RedemptionLogGroup', {
      logGroupName: `/aws/lambda/rewards-redemption-handler-${environment}`,
      retention: logRetention,
      removalPolicy: cdk.RemovalPolicy.DESTROY,
    });

    // Redemption Lambda function
    const redemptionLambda = new lambda.Function(this, 'RedemptionHandler', {
      functionName: `rewards-redemption-handler-${environment}`,
      description: 'Processes redemption transaction events from EventBridge',
      runtime: lambda.Runtime.PYTHON_3_11,
      handler: 'redemption.handler.handler',
      code: lambda.Code.fromAsset('lambda'),
      memorySize: envConfig.lambdaMemory.redemption,
      timeout: cdk.Duration.seconds(30),
      environment: {
        TABLE_NAME: this.rewardsTable.tableName,
        POWERTOOLS_SERVICE_NAME: 'redemption',
        LOG_LEVEL: 'INFO',
        ENVIRONMENT: environment,
      },
      tracing: envConfig.enableXRayTracing ? lambda.Tracing.ACTIVE : lambda.Tracing.DISABLED,
      deadLetterQueue: redemptionDLQ,
      retryAttempts: 2,
      logGroup: redemptionLogGroup,
    });

    // Grant DynamoDB read/write permissions to redemption Lambda
    this.rewardsTable.grantReadWriteData(redemptionLambda);

    // Add resource tags
    Tags.of(redemptionLambda).add('environment', environment);
    Tags.of(redemptionLambda).add('service', 'rewards-program');
    Tags.of(redemptionLambda).add('cost-center', 'customer-loyalty');

    // Connect redemption rule to redemption Lambda
    redemptionRule.addTarget(new targets.LambdaFunction(redemptionLambda, {
      deadLetterQueue: redemptionDLQ,
      maxEventAge: cdk.Duration.hours(2),
      retryAttempts: 2,
    }));

    // Dead Letter Queue for tier evaluation Lambda
    const tierEvaluationDLQ = new sqs.Queue(this, 'TierEvaluationDLQ', {
      queueName: `rewards-tier-evaluation-dlq-${environment}`,
      retentionPeriod: cdk.Duration.days(14),
      encryption: sqs.QueueEncryption.KMS_MANAGED,
    });

    // CloudWatch alarm for tier evaluation DLQ
    const tierEvaluationDLQAlarm = new cloudwatch.Alarm(this, 'TierEvaluationDLQAlarm', {
      alarmName: `rewards-tier-evaluation-dlq-messages-${environment}`,
      alarmDescription: 'Alert when tier evaluation DLQ receives messages',
      metric: tierEvaluationDLQ.metricApproximateNumberOfMessagesVisible(),
      threshold: 1,
      evaluationPeriods: 1,
      comparisonOperator: cloudwatch.ComparisonOperator.GREATER_THAN_OR_EQUAL_TO_THRESHOLD,
      treatMissingData: cloudwatch.TreatMissingData.NOT_BREACHING,
    });

    tierEvaluationDLQAlarm.addAlarmAction(new cloudwatch_actions.SnsAction(alarmTopic));

    // CloudWatch log group for tier evaluation Lambda
    const tierEvaluationLogGroup = new logs.LogGroup(this, 'TierEvaluationLogGroup', {
      logGroupName: `/aws/lambda/rewards-tier-evaluation-handler-${environment}`,
      retention: logRetention,
      removalPolicy: cdk.RemovalPolicy.DESTROY,
    });

    // Tier evaluation Lambda function
    const tierEvaluationLambda = new lambda.Function(this, 'TierEvaluationHandler', {
      functionName: `rewards-tier-evaluation-handler-${environment}`,
      description: 'Processes scheduled tier evaluation for member promotions and demotions',
      runtime: lambda.Runtime.PYTHON_3_11,
      handler: 'tier_evaluation.handler.handler',
      code: lambda.Code.fromAsset('lambda'),
      memorySize: envConfig.lambdaMemory.tierEvaluation,
      timeout: cdk.Duration.seconds(300), // 5 minutes for batch processing
      environment: {
        TABLE_NAME: this.rewardsTable.tableName,
        POWERTOOLS_SERVICE_NAME: 'tier-evaluation',
        LOG_LEVEL: 'INFO',
        ENVIRONMENT: environment,
      },
      tracing: envConfig.enableXRayTracing ? lambda.Tracing.ACTIVE : lambda.Tracing.DISABLED,
      deadLetterQueue: tierEvaluationDLQ,
      retryAttempts: 2,
      logGroup: tierEvaluationLogGroup,
    });

    // Grant DynamoDB read/write permissions to tier evaluation Lambda
    this.rewardsTable.grantReadWriteData(tierEvaluationLambda);

    // Add resource tags
    Tags.of(tierEvaluationLambda).add('environment', environment);
    Tags.of(tierEvaluationLambda).add('service', 'rewards-program');
    Tags.of(tierEvaluationLambda).add('cost-center', 'customer-loyalty');

    // Scheduled rule for tier evaluation (daily at 00:00 UTC)
    const tierEvaluationRule = new events.Rule(this, 'TierEvaluationScheduleRule', {
      ruleName: `rewards-tier-evaluation-schedule-${environment}`,
      description: 'Triggers tier evaluation handler daily at 00:00 UTC',
      schedule: events.Schedule.cron({
        minute: '0',
        hour: '0',
        day: '*',
        month: '*',
        year: '*',
      }),
    });

    // Connect scheduled rule to tier evaluation Lambda
    tierEvaluationRule.addTarget(new targets.LambdaFunction(tierEvaluationLambda, {
      deadLetterQueue: tierEvaluationDLQ,
      maxEventAge: cdk.Duration.hours(2),
      retryAttempts: 2,
    }));

    // Dead Letter Queue for expiration Lambda
    const expirationDLQ = new sqs.Queue(this, 'ExpirationDLQ', {
      queueName: `rewards-expiration-dlq-${environment}`,
      retentionPeriod: cdk.Duration.days(14),
      encryption: sqs.QueueEncryption.KMS_MANAGED,
    });

    // CloudWatch alarm for expiration DLQ
    const expirationDLQAlarm = new cloudwatch.Alarm(this, 'ExpirationDLQAlarm', {
      alarmName: `rewards-expiration-dlq-messages-${environment}`,
      alarmDescription: 'Alert when expiration DLQ receives messages',
      metric: expirationDLQ.metricApproximateNumberOfMessagesVisible(),
      threshold: 1,
      evaluationPeriods: 1,
      comparisonOperator: cloudwatch.ComparisonOperator.GREATER_THAN_OR_EQUAL_TO_THRESHOLD,
      treatMissingData: cloudwatch.TreatMissingData.NOT_BREACHING,
    });

    expirationDLQAlarm.addAlarmAction(new cloudwatch_actions.SnsAction(alarmTopic));

    // CloudWatch log group for expiration Lambda
    const expirationLogGroup = new logs.LogGroup(this, 'ExpirationLogGroup', {
      logGroupName: `/aws/lambda/rewards-expiration-handler-${environment}`,
      retention: logRetention,
      removalPolicy: cdk.RemovalPolicy.DESTROY,
    });

    // Expiration Lambda function
    const expirationLambda = new lambda.Function(this, 'ExpirationHandler', {
      functionName: `rewards-expiration-handler-${environment}`,
      description: 'Processes scheduled star expiration for Green tier members',
      runtime: lambda.Runtime.PYTHON_3_11,
      handler: 'expiration.handler.handler',
      code: lambda.Code.fromAsset('lambda'),
      memorySize: envConfig.lambdaMemory.expiration,
      timeout: cdk.Duration.seconds(300), // 5 minutes for batch processing
      environment: {
        TABLE_NAME: this.rewardsTable.tableName,
        POWERTOOLS_SERVICE_NAME: 'expiration',
        LOG_LEVEL: 'INFO',
        ENVIRONMENT: environment,
      },
      tracing: envConfig.enableXRayTracing ? lambda.Tracing.ACTIVE : lambda.Tracing.DISABLED,
      deadLetterQueue: expirationDLQ,
      retryAttempts: 2,
      logGroup: expirationLogGroup,
    });

    // Grant DynamoDB read/write permissions to expiration Lambda
    this.rewardsTable.grantReadWriteData(expirationLambda);

    // Add resource tags
    Tags.of(expirationLambda).add('environment', environment);
    Tags.of(expirationLambda).add('service', 'rewards-program');
    Tags.of(expirationLambda).add('cost-center', 'customer-loyalty');

    // Scheduled rule for expiration handler (daily at 01:00 UTC)
    const expirationRule = new events.Rule(this, 'ExpirationScheduleRule', {
      ruleName: `rewards-expiration-schedule-${environment}`,
      description: 'Triggers star expiration handler daily at 01:00 UTC',
      schedule: events.Schedule.cron({
        minute: '0',
        hour: '1',
        day: '*',
        month: '*',
        year: '*',
      }),
    });

    // Connect scheduled rule to expiration Lambda
    expirationRule.addTarget(new targets.LambdaFunction(expirationLambda, {
      deadLetterQueue: expirationDLQ,
      maxEventAge: cdk.Duration.hours(2),
      retryAttempts: 2,
    }));

    // CloudWatch log group for API Gateway access logs
    const apiLogGroup = new logs.LogGroup(this, 'RewardsApiLogGroup', {
      logGroupName: `/aws/apigateway/rewards-program-${environment}`,
      retention: logRetention,
      removalPolicy: cdk.RemovalPolicy.DESTROY,
    });

    // REST API Gateway with regional endpoint
    this.rewardsApi = new apigateway.RestApi(this, 'RewardsApi', {
      restApiName: resolveName(namingConventions.apiName || 'rewards-program-api-${environment}'),
      description: `REST API for querying member balances and transaction history - ${environment.toUpperCase()}`,
      endpointConfiguration: {
        types: [apigateway.EndpointType.REGIONAL],
      },
      deployOptions: {
        stageName: 'v1',
        throttlingRateLimit: envConfig.apiThrottling.rateLimit,
        throttlingBurstLimit: envConfig.apiThrottling.burstLimit,
        loggingLevel: envConfig.enableDetailedMonitoring 
          ? apigateway.MethodLoggingLevel.INFO 
          : apigateway.MethodLoggingLevel.ERROR,
        dataTraceEnabled: envConfig.enableDetailedMonitoring,
        accessLogDestination: new apigateway.LogGroupLogDestination(apiLogGroup),
        accessLogFormat: apigateway.AccessLogFormat.jsonWithStandardFields({
          caller: true,
          httpMethod: true,
          ip: true,
          protocol: true,
          requestTime: true,
          resourcePath: true,
          responseLength: true,
          status: true,
          user: true,
        }),
      },
      defaultCorsPreflightOptions: {
        allowOrigins: apigateway.Cors.ALL_ORIGINS,
        allowMethods: ['GET', 'OPTIONS'],
        allowHeaders: [
          'Content-Type',
          'X-Amz-Date',
          'Authorization',
          'X-Api-Key',
          'X-Amz-Security-Token',
        ],
        maxAge: cdk.Duration.hours(1),
      },
      cloudWatchRole: true,
    });

    // Add resource tags to API Gateway
    Tags.of(this.rewardsApi).add('environment', environment);
    Tags.of(this.rewardsApi).add('service', 'rewards-program');
    Tags.of(this.rewardsApi).add('cost-center', 'customer-loyalty');

    // Request validator for query parameters
    const requestValidator = new apigateway.RequestValidator(this, 'RewardsApiRequestValidator', {
      restApi: this.rewardsApi,
      requestValidatorName: 'rewards-query-validator',
      validateRequestParameters: true,
      validateRequestBody: false,
    });

    // Members resource: /v1/members
    const membersResource = this.rewardsApi.root.addResource('members');

    // Member by ID resource: /v1/members/{membershipId}
    const memberResource = membersResource.addResource('{membershipId}');

    // Transactions resource: /v1/members/{membershipId}/transactions
    const transactionsResource = memberResource.addResource('transactions');

    // CloudWatch log group for query Lambda
    const queryLogGroup = new logs.LogGroup(this, 'QueryLogGroup', {
      logGroupName: `/aws/lambda/rewards-query-handler-${environment}`,
      retention: logRetention,
      removalPolicy: cdk.RemovalPolicy.DESTROY,
    });

    // Query Lambda function for API Gateway endpoints
    const queryLambda = new lambda.Function(this, 'QueryHandler', {
      functionName: `rewards-query-handler-${environment}`,
      description: 'Handles API Gateway requests for member data and transaction history',
      runtime: lambda.Runtime.PYTHON_3_11,
      handler: 'query.handler.handler',
      code: lambda.Code.fromAsset('lambda'),
      memorySize: envConfig.lambdaMemory.query,
      timeout: cdk.Duration.seconds(10),
      environment: {
        TABLE_NAME: this.rewardsTable.tableName,
        POWERTOOLS_SERVICE_NAME: 'query',
        LOG_LEVEL: 'INFO',
        ENVIRONMENT: environment,
      },
      tracing: envConfig.enableXRayTracing ? lambda.Tracing.ACTIVE : lambda.Tracing.DISABLED,
      logGroup: queryLogGroup,
    });

    // Grant DynamoDB read permissions to query Lambda
    this.rewardsTable.grantReadData(queryLambda);

    // Add resource tags
    Tags.of(queryLambda).add('environment', environment);
    Tags.of(queryLambda).add('service', 'rewards-program');
    Tags.of(queryLambda).add('cost-center', 'customer-loyalty');

    // Lambda integration for member profile endpoint
    const memberIntegration = new apigateway.LambdaIntegration(queryLambda, {
      requestTemplates: { 'application/json': '{ "statusCode": "200" }' },
      proxy: true,
    });

    // Lambda integration for transaction history endpoint
    const transactionIntegration = new apigateway.LambdaIntegration(queryLambda, {
      requestTemplates: { 'application/json': '{ "statusCode": "200" }' },
      proxy: true,
    });

    // Add GET method to member resource
    memberResource.addMethod('GET', memberIntegration, {
      requestValidator: requestValidator,
      requestParameters: {
        'method.request.path.membershipId': true,
      },
      methodResponses: [
        {
          statusCode: '200',
          responseModels: {
            'application/json': apigateway.Model.EMPTY_MODEL,
          },
        },
        {
          statusCode: '400',
          responseModels: {
            'application/json': apigateway.Model.ERROR_MODEL,
          },
        },
        {
          statusCode: '404',
          responseModels: {
            'application/json': apigateway.Model.ERROR_MODEL,
          },
        },
        {
          statusCode: '500',
          responseModels: {
            'application/json': apigateway.Model.ERROR_MODEL,
          },
        },
      ],
    });

    // Add GET method to transactions resource
    transactionsResource.addMethod('GET', transactionIntegration, {
      requestValidator: requestValidator,
      requestParameters: {
        'method.request.path.membershipId': true,
        'method.request.querystring.limit': false,
        'method.request.querystring.nextToken': false,
      },
      methodResponses: [
        {
          statusCode: '200',
          responseModels: {
            'application/json': apigateway.Model.EMPTY_MODEL,
          },
        },
        {
          statusCode: '400',
          responseModels: {
            'application/json': apigateway.Model.ERROR_MODEL,
          },
        },
        {
          statusCode: '404',
          responseModels: {
            'application/json': apigateway.Model.ERROR_MODEL,
          },
        },
        {
          statusCode: '500',
          responseModels: {
            'application/json': apigateway.Model.ERROR_MODEL,
          },
        },
      ],
    });

    // Add usage plan for rate limiting
    const usagePlan = this.rewardsApi.addUsagePlan('RewardsApiUsagePlan', {
      name: `rewards-standard-plan-${environment}`,
      description: `Standard usage plan for rewards API - ${environment.toUpperCase()}`,
      throttle: {
        rateLimit: envConfig.apiThrottling.rateLimit,
        burstLimit: envConfig.apiThrottling.burstLimit,
      },
      quota: {
        limit: envConfig.apiThrottling.rateLimit * 100, // 100x rate limit per day
        period: apigateway.Period.DAY,
      },
    });

    usagePlan.addApiStage({
      stage: this.rewardsApi.deploymentStage,
    });

    // Output the table name and ARN
    new cdk.CfnOutput(this, 'RewardsTableName', {
      value: this.rewardsTable.tableName,
      description: 'DynamoDB table name for rewards program',
      exportName: 'RewardsTableName',
    });

    new cdk.CfnOutput(this, 'RewardsTableArn', {
      value: this.rewardsTable.tableArn,
      description: 'DynamoDB table ARN for rewards program',
      exportName: 'RewardsTableArn',
    });

    // Output the event bus name and ARN
    new cdk.CfnOutput(this, 'RewardsEventBusName', {
      value: this.rewardsEventBus.eventBusName,
      description: 'EventBridge event bus name for rewards program',
      exportName: 'RewardsEventBusName',
    });

    new cdk.CfnOutput(this, 'RewardsEventBusArn', {
      value: this.rewardsEventBus.eventBusArn,
      description: 'EventBridge event bus ARN for rewards program',
      exportName: 'RewardsEventBusArn',
    });

    // ========================================
    // MONITORING AND OBSERVABILITY
    // ========================================

    // Main CloudWatch Dashboard for Rewards Program
    const mainDashboard = new cloudwatch.Dashboard(this, 'RewardsProgramDashboard', {
      dashboardName: `rewards-program-overview-${environment}`,
      defaultInterval: cdk.Duration.hours(1),
    });

    // Lambda Functions Overview Widget
    const lambdaOverviewWidget = new cloudwatch.GraphWidget({
      title: 'Lambda Functions Overview',
      width: 24,
      height: 6,
      left: [
        enrollmentLambda.metricInvocations({ label: 'Enrollment Invocations' }),
        purchaseLambda.metricInvocations({ label: 'Purchase Invocations' }),
        redemptionLambda.metricInvocations({ label: 'Redemption Invocations' }),
        tierEvaluationLambda.metricInvocations({ label: 'Tier Evaluation Invocations' }),
        expirationLambda.metricInvocations({ label: 'Expiration Invocations' }),
        queryLambda.metricInvocations({ label: 'Query Invocations' }),
      ],
      right: [
        enrollmentLambda.metricErrors({ label: 'Enrollment Errors' }),
        purchaseLambda.metricErrors({ label: 'Purchase Errors' }),
        redemptionLambda.metricErrors({ label: 'Redemption Errors' }),
        tierEvaluationLambda.metricErrors({ label: 'Tier Evaluation Errors' }),
        expirationLambda.metricErrors({ label: 'Expiration Errors' }),
        queryLambda.metricErrors({ label: 'Query Errors' }),
      ],
    });

    // Lambda Duration Widget
    const lambdaDurationWidget = new cloudwatch.GraphWidget({
      title: 'Lambda Function Duration (P99)',
      width: 12,
      height: 6,
      left: [
        enrollmentLambda.metricDuration({ statistic: 'p99', label: 'Enrollment P99' }),
        purchaseLambda.metricDuration({ statistic: 'p99', label: 'Purchase P99' }),
        redemptionLambda.metricDuration({ statistic: 'p99', label: 'Redemption P99' }),
        queryLambda.metricDuration({ statistic: 'p99', label: 'Query P99' }),
      ],
    });

    // DynamoDB Metrics Widget
    const dynamoDbWidget = new cloudwatch.GraphWidget({
      title: 'DynamoDB Metrics',
      width: 12,
      height: 6,
      left: [
        this.rewardsTable.metricConsumedReadCapacityUnits({ label: 'Read Capacity' }),
        this.rewardsTable.metricConsumedWriteCapacityUnits({ label: 'Write Capacity' }),
      ],
      right: [
        this.rewardsTable.metricThrottledRequestsForOperation('GetItem', { label: 'GetItem Throttles' }),
        new cloudwatch.Metric({
          namespace: 'AWS/DynamoDB',
          metricName: 'SuccessfulRequestLatency',
          dimensionsMap: {
            TableName: this.rewardsTable.tableName,
            Operation: 'GetItem',
          },
          statistic: 'Average',
          label: 'GetItem Latency',
        }),
      ],
    });

    // API Gateway Metrics Widget
    const apiGatewayWidget = new cloudwatch.GraphWidget({
      title: 'API Gateway Metrics',
      width: 12,
      height: 6,
      left: [
        new cloudwatch.Metric({
          namespace: 'AWS/ApiGateway',
          metricName: 'Count',
          dimensionsMap: {
            ApiName: this.rewardsApi.restApiName,
          },
          statistic: 'Sum',
          label: 'Total Requests',
        }),
        new cloudwatch.Metric({
          namespace: 'AWS/ApiGateway',
          metricName: 'Latency',
          dimensionsMap: {
            ApiName: this.rewardsApi.restApiName,
          },
          statistic: 'Average',
          label: 'Average Latency',
        }),
      ],
      right: [
        new cloudwatch.Metric({
          namespace: 'AWS/ApiGateway',
          metricName: '4XXError',
          dimensionsMap: {
            ApiName: this.rewardsApi.restApiName,
          },
          statistic: 'Sum',
          label: '4XX Errors',
        }),
        new cloudwatch.Metric({
          namespace: 'AWS/ApiGateway',
          metricName: '5XXError',
          dimensionsMap: {
            ApiName: this.rewardsApi.restApiName,
          },
          statistic: 'Sum',
          label: '5XX Errors',
        }),
      ],
    });

    // EventBridge Metrics Widget
    const eventBridgeWidget = new cloudwatch.GraphWidget({
      title: 'EventBridge Metrics',
      width: 12,
      height: 6,
      left: [
        new cloudwatch.Metric({
          namespace: 'AWS/Events',
          metricName: 'InvocationsCount',
          dimensionsMap: {
            RuleName: signupRule.ruleName,
          },
          statistic: 'Sum',
          label: 'Signup Rule Invocations',
        }),
        new cloudwatch.Metric({
          namespace: 'AWS/Events',
          metricName: 'InvocationsCount',
          dimensionsMap: {
            RuleName: purchaseRule.ruleName,
          },
          statistic: 'Sum',
          label: 'Purchase Rule Invocations',
        }),
        new cloudwatch.Metric({
          namespace: 'AWS/Events',
          metricName: 'InvocationsCount',
          dimensionsMap: {
            RuleName: redemptionRule.ruleName,
          },
          statistic: 'Sum',
          label: 'Redemption Rule Invocations',
        }),
      ],
    });

    // DLQ Messages Widget
    const dlqWidget = new cloudwatch.GraphWidget({
      title: 'Dead Letter Queue Messages',
      width: 24,
      height: 6,
      left: [
        enrollmentDLQ.metricApproximateNumberOfMessagesVisible({ label: 'Enrollment DLQ' }),
        purchaseDLQ.metricApproximateNumberOfMessagesVisible({ label: 'Purchase DLQ' }),
        redemptionDLQ.metricApproximateNumberOfMessagesVisible({ label: 'Redemption DLQ' }),
        tierEvaluationDLQ.metricApproximateNumberOfMessagesVisible({ label: 'Tier Evaluation DLQ' }),
        expirationDLQ.metricApproximateNumberOfMessagesVisible({ label: 'Expiration DLQ' }),
      ],
    });

    // Add widgets to main dashboard
    mainDashboard.addWidgets(
      lambdaOverviewWidget,
      lambdaDurationWidget,
      dynamoDbWidget,
      apiGatewayWidget,
      eventBridgeWidget,
      dlqWidget
    );

    // Individual Lambda Function Dashboards
    const createLambdaDashboard = (
      lambdaFunction: lambda.Function,
      dashboardName: string,
      functionName: string
    ) => {
      const dashboard = new cloudwatch.Dashboard(this, `${dashboardName}Dashboard`, {
        dashboardName: `rewards-${dashboardName.toLowerCase()}-${environment}`,
        defaultInterval: cdk.Duration.hours(1),
      });

      const invocationsWidget = new cloudwatch.GraphWidget({
        title: `${functionName} - Invocations and Errors`,
        width: 12,
        height: 6,
        left: [lambdaFunction.metricInvocations({ label: 'Invocations' })],
        right: [lambdaFunction.metricErrors({ label: 'Errors' })],
      });

      const durationWidget = new cloudwatch.GraphWidget({
        title: `${functionName} - Duration`,
        width: 12,
        height: 6,
        left: [
          lambdaFunction.metricDuration({ statistic: 'Average', label: 'Average Duration' }),
          lambdaFunction.metricDuration({ statistic: 'p99', label: 'P99 Duration' }),
          lambdaFunction.metricDuration({ statistic: 'Maximum', label: 'Max Duration' }),
        ],
      });

      const throttlesWidget = new cloudwatch.GraphWidget({
        title: `${functionName} - Throttles and Concurrent Executions`,
        width: 12,
        height: 6,
        left: [
          lambdaFunction.metricThrottles({ label: 'Throttles' }),
          new cloudwatch.Metric({
            namespace: 'AWS/Lambda',
            metricName: 'ConcurrentExecutions',
            dimensionsMap: {
              FunctionName: lambdaFunction.functionName,
            },
            statistic: 'Maximum',
            label: 'Concurrent Executions',
          }),
        ],
      });

      const memoryWidget = new cloudwatch.GraphWidget({
        title: `${functionName} - Memory Utilization`,
        width: 12,
        height: 6,
        left: [
          new cloudwatch.Metric({
            namespace: 'AWS/Lambda',
            metricName: 'MemoryUtilization',
            dimensionsMap: {
              FunctionName: lambdaFunction.functionName,
            },
            statistic: 'Average',
            label: 'Memory Utilization %',
          }),
        ],
      });

      dashboard.addWidgets(invocationsWidget, durationWidget, throttlesWidget, memoryWidget);
      return dashboard;
    };

    // Create individual dashboards for each Lambda function
    createLambdaDashboard(enrollmentLambda, 'Enrollment', 'Enrollment Handler');
    createLambdaDashboard(purchaseLambda, 'Purchase', 'Purchase Handler');
    createLambdaDashboard(redemptionLambda, 'Redemption', 'Redemption Handler');
    createLambdaDashboard(tierEvaluationLambda, 'TierEvaluation', 'Tier Evaluation Handler');
    createLambdaDashboard(expirationLambda, 'Expiration', 'Expiration Handler');
    createLambdaDashboard(queryLambda, 'Query', 'Query Handler');

    // ========================================
    // ADDITIONAL CLOUDWATCH ALARMS
    // ========================================

    // Lambda Error Rate Alarms (> 5%)
    const createErrorRateAlarm = (lambdaFunction: lambda.Function, alarmName: string) => {
      const errorRateAlarm = new cloudwatch.Alarm(this, `${alarmName}ErrorRateAlarm`, {
        alarmName: `rewards-${alarmName.toLowerCase()}-error-rate-${environment}`,
        alarmDescription: `Alert when ${alarmName} Lambda error rate exceeds 5% - ${environment.toUpperCase()}`,
        metric: new cloudwatch.MathExpression({
          expression: '(errors / invocations) * 100',
          usingMetrics: {
            errors: lambdaFunction.metricErrors({ statistic: 'Sum' }),
            invocations: lambdaFunction.metricInvocations({ statistic: 'Sum' }),
          },
          label: 'Error Rate %',
        }),
        threshold: 5,
        evaluationPeriods: 2,
        comparisonOperator: cloudwatch.ComparisonOperator.GREATER_THAN_THRESHOLD,
        treatMissingData: cloudwatch.TreatMissingData.NOT_BREACHING,
      });
      errorRateAlarm.addAlarmAction(new cloudwatch_actions.SnsAction(alarmTopic));
      return errorRateAlarm;
    };

    createErrorRateAlarm(enrollmentLambda, 'Enrollment');
    createErrorRateAlarm(purchaseLambda, 'Purchase');
    createErrorRateAlarm(redemptionLambda, 'Redemption');
    createErrorRateAlarm(tierEvaluationLambda, 'TierEvaluation');
    createErrorRateAlarm(expirationLambda, 'Expiration');
    createErrorRateAlarm(queryLambda, 'Query');

    // API Gateway 5XX Error Rate Alarm (> 1%)
    const apiGateway5xxAlarm = new cloudwatch.Alarm(this, 'ApiGateway5xxErrorRateAlarm', {
      alarmName: `rewards-api-5xx-error-rate-${environment}`,
      alarmDescription: `Alert when API Gateway 5XX error rate exceeds 1% - ${environment.toUpperCase()}`,
      metric: new cloudwatch.MathExpression({
        expression: '(errors5xx / totalRequests) * 100',
        usingMetrics: {
          errors5xx: new cloudwatch.Metric({
            namespace: 'AWS/ApiGateway',
            metricName: '5XXError',
            dimensionsMap: {
              ApiName: this.rewardsApi.restApiName,
            },
            statistic: 'Sum',
          }),
          totalRequests: new cloudwatch.Metric({
            namespace: 'AWS/ApiGateway',
            metricName: 'Count',
            dimensionsMap: {
              ApiName: this.rewardsApi.restApiName,
            },
            statistic: 'Sum',
          }),
        },
        label: '5XX Error Rate %',
      }),
      threshold: 1,
      evaluationPeriods: 2,
      comparisonOperator: cloudwatch.ComparisonOperator.GREATER_THAN_THRESHOLD,
      treatMissingData: cloudwatch.TreatMissingData.NOT_BREACHING,
    });

    apiGateway5xxAlarm.addAlarmAction(new cloudwatch_actions.SnsAction(alarmTopic));

    // DynamoDB Throttling Alarm
    const dynamoDbThrottleAlarm = new cloudwatch.Alarm(this, 'DynamoDbThrottleAlarm', {
      alarmName: `rewards-dynamodb-throttling-${environment}`,
      alarmDescription: `Alert when DynamoDB experiences throttling events - ${environment.toUpperCase()}`,
      metric: this.rewardsTable.metricThrottledRequestsForOperation('GetItem'),
      threshold: 1,
      evaluationPeriods: 1,
      comparisonOperator: cloudwatch.ComparisonOperator.GREATER_THAN_OR_EQUAL_TO_THRESHOLD,
      treatMissingData: cloudwatch.TreatMissingData.NOT_BREACHING,
    });

    dynamoDbThrottleAlarm.addAlarmAction(new cloudwatch_actions.SnsAction(alarmTopic));

    // Query Handler P99 Latency Alarm (> 200ms)
    const queryLatencyAlarm = new cloudwatch.Alarm(this, 'QueryLatencyAlarm', {
      alarmName: `rewards-query-p99-latency-${environment}`,
      alarmDescription: `Alert when Query handler P99 latency exceeds 200ms - ${environment.toUpperCase()}`,
      metric: queryLambda.metricDuration({ statistic: 'p99' }),
      threshold: 200,
      evaluationPeriods: 2,
      comparisonOperator: cloudwatch.ComparisonOperator.GREATER_THAN_THRESHOLD,
      treatMissingData: cloudwatch.TreatMissingData.NOT_BREACHING,
    });

    queryLatencyAlarm.addAlarmAction(new cloudwatch_actions.SnsAction(alarmTopic));

    // Output monitoring resources
    new cdk.CfnOutput(this, 'MainDashboardUrl', {
      value: `https://${this.region}.console.aws.amazon.com/cloudwatch/home?region=${this.region}#dashboards:name=${mainDashboard.dashboardName}`,
      description: 'CloudWatch main dashboard URL',
      exportName: 'MainDashboardUrl',
    });

    new cdk.CfnOutput(this, 'AlarmTopicArn', {
      value: alarmTopic.topicArn,
      description: 'SNS topic ARN for alarm notifications',
      exportName: 'AlarmTopicArn',
    });
  }
}
