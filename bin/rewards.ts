#!/usr/bin/env node
import * as cdk from 'aws-cdk-lib/core';
import { RewardsStack } from '../lib/rewards-stack';
import { EnvironmentConfig, NamingConventions } from '../lib/environment-config';

const app = new cdk.App();

// Get environment from context or environment variable, default to 'dev'
const environment = app.node.tryGetContext('environment') || process.env.ENVIRONMENT || 'dev';

// Get environment-specific configuration from context
const envConfig: EnvironmentConfig = app.node.tryGetContext('environments')?.[environment];
if (!envConfig) {
  throw new Error(`Environment configuration not found for: ${environment}. Available environments: ${Object.keys(app.node.tryGetContext('environments') || {}).join(', ')}`);
}

// Get naming conventions from context
const namingConventions: NamingConventions = app.node.tryGetContext('namingConventions') || {};

// Get stack tags from context and replace environment placeholder
const stackTags = app.node.tryGetContext('stackTags') || {};
const processedTags: { [key: string]: string } = {};
Object.entries(stackTags).forEach(([key, value]) => {
  processedTags[key] = typeof value === 'string' ? value.replace('${ENVIRONMENT}', environment) : value as string;
});

// Create stack name using naming convention
const stackName = namingConventions.stackName?.replace('${environment}', environment) || `RewardsStack-${environment}`;

const stack = new RewardsStack(app, stackName, {
  env: {
    account: envConfig.account || process.env.CDK_DEFAULT_ACCOUNT,
    region: envConfig.region || process.env.CDK_DEFAULT_REGION || 'us-east-1',
  },
  description: `Rewards Program Backend - ${environment.toUpperCase()} environment`,
  tags: processedTags,
  environment,
  envConfig,
  namingConventions,
});

// Add environment-specific tags to the stack
cdk.Tags.of(stack).add('Environment', environment);
cdk.Tags.of(stack).add('DeployedBy', process.env.USER || 'unknown');
cdk.Tags.of(stack).add('DeployedAt', new Date().toISOString());
