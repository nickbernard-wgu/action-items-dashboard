import * as cdk from 'aws-cdk-lib';
import { Construct } from 'constructs';
import * as dynamodb from 'aws-cdk-lib/aws-dynamodb';
import * as secretsmanager from 'aws-cdk-lib/aws-secretsmanager';
import * as amplify from '@aws-cdk/aws-amplify-alpha';
import * as codebuild from 'aws-cdk-lib/aws-codebuild';

export class InfraStack extends cdk.Stack {
  constructor(scope: Construct, id: string, props?: cdk.StackProps) {
    super(scope, id, props);

    // DynamoDB table: PK = item_id (String), GSI on status
    const actionItemsTable = new dynamodb.Table(this, 'ActionItemsTable', {
      tableName: 'action-items',
      partitionKey: { name: 'item_id', type: dynamodb.AttributeType.STRING },
      billingMode: dynamodb.BillingMode.PAY_PER_REQUEST,
      removalPolicy: cdk.RemovalPolicy.RETAIN,
    });

    actionItemsTable.addGlobalSecondaryIndex({
      indexName: 'status-index',
      partitionKey: { name: 'status', type: dynamodb.AttributeType.STRING },
      projectionType: dynamodb.ProjectionType.ALL,
    });

    // Secrets Manager placeholder for Confluence credentials
    const confluenceSecret = new secretsmanager.Secret(this, 'ConfluenceSecret', {
      secretName: 'action-items-dashboard/confluence-credentials',
      description: 'Confluence API token for action items extractor Lambda',
      generateSecretString: {
        secretStringTemplate: JSON.stringify({ username: 'placeholder' }),
        generateStringKey: 'api_token',
      },
    });

    // AWS Amplify app connected to main branch
    const amplifyApp = new amplify.App(this, 'ActionItemsApp', {
      appName: 'action-items-dashboard',
      buildSpec: codebuild.BuildSpec.fromObjectToYaml({
        version: '1.0',
        frontend: {
          phases: {
            preBuild: { commands: ['cd frontend', 'npm ci'] },
            build: { commands: ['npm run build'] },
          },
          artifacts: { baseDirectory: 'frontend/dist', files: ['**/*'] },
          cache: { paths: ['frontend/node_modules/**/*'] },
        },
      }),
    });

    amplifyApp.addBranch('main', {
      autoBuild: true,
    });

    // Outputs
    new cdk.CfnOutput(this, 'TableName', { value: actionItemsTable.tableName });
    new cdk.CfnOutput(this, 'SecretArn', { value: confluenceSecret.secretArn });
    new cdk.CfnOutput(this, 'AmplifyAppId', { value: amplifyApp.appId });
  }
}
