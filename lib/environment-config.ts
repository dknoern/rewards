import * as cdk from 'aws-cdk-lib/core';

export interface EnvironmentConfig {
  account: string;
  region: string;
  removalPolicy: 'DESTROY' | 'RETAIN';
  logRetention: number;
  enableDetailedMonitoring: boolean;
  enableXRayTracing: boolean;
  apiThrottling: {
    rateLimit: number;
    burstLimit: number;
  };
  lambdaMemory: {
    query: number;
    enrollment: number;
    purchase: number;
    redemption: number;
    tierEvaluation: number;
    expiration: number;
  };
}

export interface NamingConventions {
  stackName: string;
  resourcePrefix: string;
  tableName: string;
  eventBusName: string;
  apiName: string;
}

export interface RewardsStackProps extends cdk.StackProps {
  environment: string;
  envConfig: EnvironmentConfig;
  namingConventions: NamingConventions;
}