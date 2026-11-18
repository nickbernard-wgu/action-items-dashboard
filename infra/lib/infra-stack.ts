import * as cdk from 'aws-cdk-lib';
import { Construct } from 'constructs';
import * as dynamodb from 'aws-cdk-lib/aws-dynamodb';
import * as secretsmanager from 'aws-cdk-lib/aws-secretsmanager';
import * as amplify from '@aws-cdk/aws-amplify-alpha';
import * as codebuild from 'aws-cdk-lib/aws-codebuild';
import * as lambda from 'aws-cdk-lib/aws-lambda';
import * as apigatewayv2 from 'aws-cdk-lib/aws-apigatewayv2';
import * as apigatewayv2integrations from 'aws-cdk-lib/aws-apigatewayv2-integrations';
import * as path from 'path';

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

    // Lambda: GET /action-items
    const getActionItemsLambda = new lambda.Function(this, 'GetActionItemsLambda', {
      functionName: 'get-action-items',
      runtime: lambda.Runtime.PYTHON_3_11,
      handler: 'handler.lambda_handler',
      code: lambda.Code.fromAsset(path.join(__dirname, '../../lambdas/api/get_action_items')),
      environment: {
        TABLE_NAME: actionItemsTable.tableName,
      },
    });

    actionItemsTable.grantReadData(getActionItemsLambda);

    // HTTP API Gateway
    const httpApi = new apigatewayv2.HttpApi(this, 'ActionItemsHttpApi', {
      apiName: 'action-items-api',
      corsPreflight: {
        allowHeaders: ['Content-Type'],
        allowMethods: [apigatewayv2.CorsHttpMethod.GET, apigatewayv2.CorsHttpMethod.OPTIONS],
        allowOrigins: ['*'],
      },
    });

    httpApi.addRoutes({
      path: '/action-items',
      methods: [apigatewayv2.HttpMethod.GET],
      integration: new apigatewayv2integrations.HttpLambdaIntegration('GetActionItemsIntegration', getActionItemsLambda),
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
    new cdk.CfnOutput(this, 'ActionItemsApiUrl', {
      value: httpApi.apiEndpoint,
      exportName: 'ActionItemsApiUrl',
    });
  }
}
