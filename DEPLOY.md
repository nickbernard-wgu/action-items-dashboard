# Deploy (backend)

This repo is the backend and the original frontend source. The hosted frontend lives in
`WGUProductPOC/action-items-dashboard`, which the org Amplify pipeline builds and hosts.
This stack deploys only DynamoDB, Secrets Manager, three Lambdas, API Gateway and the 15-minute schedule.

Run from a shell with AWS credentials for the target account and region.

1. **Bootstrap CDK** (first time per account and region): `cd infra && npm ci && npx cdk bootstrap`
2. **Deploy**: `npx cdk deploy`. Note the output `ActionItemsApiUrl`: the frontend repo needs it.
3. **Set the Confluence secret.** Secret `action-items-dashboard/confluence-credentials` must be JSON with:
   - `site_url`: bare host, for example `wgu.atlassian.net` (no `https://`)
   - `username`: the Atlassian account email
   - `api_token`: an Atlassian API token for that account

   ```
   aws secretsmanager put-secret-value \
     --secret-id action-items-dashboard/confluence-credentials \
     --secret-string '{"site_url":"<host>","username":"<email>","api_token":"<token>"}'
   ```
4. **Run the first sync**: `aws lambda invoke --function-name action-items-extractor /dev/stdout`,
   then `curl "<ActionItemsApiUrl>/action-items"` should return items and `last_synced`.
5. **Give the `ActionItemsApiUrl` to the frontend repo** (`frontend/.env.production`, `VITE_API_URL=...`).
6. **After the frontend URL is known**, tighten CORS and redeploy:
   `npx cdk deploy -c frontendOrigin=https://main.<appId>.amplifyapp.com`
   CORS only constrains browsers. The API has no auth, so anyone who has its URL can still call it
   directly. The default stage throttles to 10 requests per second (burst 20).
7. **Smoke test**: mark one throwaway item complete and confirm the checkbox is checked on the Confluence page.

The extractor then runs every 15 minutes.
