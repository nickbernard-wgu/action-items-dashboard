# Action Items Dashboard

A web dashboard for tracking action items extracted from Confluence meeting notes. Hosted on AWS Amplify, backed by DynamoDB, with Python Lambdas for data sync.

## Repository Layout

```
action-items-dashboard/
├── frontend/   # React + Vite app
├── lambdas/    # Python Lambda functions
└── infra/      # AWS CDK (TypeScript) infrastructure
```

## Prerequisites

- Node.js 20+
- Python 3.11+
- AWS CLI configured (`aws configure`)
- AWS CDK CLI (`npm install -g aws-cdk`)
- GitHub CLI (`gh`)

## Bootstrap CDK

First-time setup — run once per AWS account/region:

```bash
cd infra
npm ci
cdk bootstrap
```

Deploy the stack:

```bash
cdk deploy
```

This provisions:
- DynamoDB table `action-items` (PK: `item_id`, GSI on `status`)
- Secrets Manager secret for Confluence credentials
- AWS Amplify app connected to the `main` branch

After deploy, populate the Confluence secret in AWS Secrets Manager:
```bash
aws secretsmanager put-secret-value \
  --secret-id action-items-dashboard/confluence-credentials \
  --secret-string '{"username":"your-email@wgu.edu","api_token":"your-confluence-api-token"}'
```

## Run the Frontend Locally

```bash
cd frontend
npm ci
npm run dev
```

Opens at http://localhost:5173.

## Run Frontend Tests

```bash
cd frontend
npm test
```

## Run CDK Synth (dry run)

```bash
cd infra
npm ci
npx cdk synth
```

## CI

GitHub Actions runs on every push to `main`:
- `frontend-test`: runs `npm test`
- `infra-synth`: runs `cdk synth`

Both must pass.
