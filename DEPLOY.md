# Deploy

Run once per AWS account and region, from a shell with AWS credentials for the target account.

1. **Bootstrap CDK** (first time only): `cd infra && npx cdk bootstrap`
2. **Deploy**: `npx cdk deploy`. Note the outputs `ActionItemsApiUrl`, `AmplifyAppId`, `SecretArn`.
3. **Set the Confluence secret.** Secret `action-items-dashboard/confluence-credentials` must be JSON with these keys:
   - `site_url`: bare host, for example `wgu.atlassian.net` (no `https://`)
   - `username`: the Atlassian account email
   - `api_token`: an Atlassian API token for that account

   ```
   aws secretsmanager put-secret-value \
     --secret-id action-items-dashboard/confluence-credentials \
     --secret-string '{"site_url":"<host>","username":"<email>","api_token":"<token>"}'
   ```
4. **Run the first sync**: `aws lambda invoke --function-name action-items-extractor /dev/stdout`
   then check `curl "$ActionItemsApiUrl/action-items"` returns items.
5. **Connect Amplify to GitHub.** In the Amplify console, open app `action-items-dashboard`, connect
   repository `nickbernard-wgu/action-items-dashboard`, branch `main`. `VITE_API_URL` is already set by the stack.
   Trigger a build and open the Amplify URL.
6. **Smoke test**: mark one throwaway item complete and confirm the checkbox is checked on the Confluence page.

The extractor then runs every 15 minutes.
