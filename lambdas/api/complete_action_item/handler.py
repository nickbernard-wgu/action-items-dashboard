import json
import os
import re
import logging

import boto3
import requests
from botocore.exceptions import ClientError
from requests.auth import HTTPBasicAuth

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Match a full <ac:task> block (non-greedy, DOTALL)
_TASK_BLOCK_RE = re.compile(
    r'(<ac:task>.*?</ac:task>)',
    re.DOTALL,
)

# Within a task block, extract status and body text
_TASK_STATUS_RE = re.compile(r'<ac:task-status>(.*?)</ac:task-status>', re.DOTALL)
_TASK_BODY_RE = re.compile(r'<ac:task-body>(.*?)</ac:task-body>', re.DOTALL)

# Strip all HTML tags for plain-text comparison
_TAG_RE = re.compile(r'<[^>]+>')


def _strip_html(text):
    return _TAG_RE.sub('', text).strip()


def lambda_handler(event, context):
    table_name = os.environ['TABLE_NAME']
    secret_name = os.environ['SECRET_NAME']
    region = os.environ.get('AWS_DEFAULT_REGION', os.environ.get('AWS_REGION', 'us-east-1'))

    item_id = event['pathParameters']['id']

    # ── Step 1: DynamoDB lookup ──────────────────────────────────────────────
    logger.info(json.dumps({'step': 'dynamodb_lookup', 'item_id': item_id}))

    dynamodb = boto3.resource('dynamodb', region_name=region)
    table = dynamodb.Table(table_name)

    try:
        response = table.get_item(Key={'item_id': item_id})
    except ClientError as exc:
        logger.error(json.dumps({'step': 'dynamodb_lookup_error', 'error': str(exc)}))
        return _resp(500, {'error': 'Internal server error'})

    item = response.get('Item')
    if not item:
        logger.info(json.dumps({'step': 'dynamodb_lookup', 'result': 'not_found', 'item_id': item_id}))
        return _resp(404, {'error': 'Item not found'})

    logger.info(json.dumps({'step': 'dynamodb_lookup', 'result': 'found', 'item_id': item_id}))

    item_text = item.get('text', '')
    source_page_id = item.get('source_page_id', '')

    # ── Step 2: Fetch Confluence credentials from Secrets Manager ────────────
    logger.info(json.dumps({'step': 'secrets_manager_get', 'secret_name': secret_name}))

    secrets_client = boto3.client('secretsmanager', region_name=region)
    try:
        secret_resp = secrets_client.get_secret_value(SecretId=secret_name)
    except ClientError as exc:
        logger.error(json.dumps({'step': 'secrets_manager_error', 'error': str(exc)}))
        return _resp(500, {'error': 'Internal server error'})

    creds = json.loads(secret_resp['SecretString'])
    api_token = creds['api_token']
    email = creds['email']
    site_url = creds['site_url']

    logger.info(json.dumps({'step': 'secrets_manager_get', 'result': 'ok'}))

    # ── Step 3: GET Confluence page (storage body + version) ─────────────────
    get_url = f'https://{site_url}/wiki/api/v2/pages/{source_page_id}?body-format=storage'
    logger.info(json.dumps({'step': 'confluence_get', 'url': get_url}))

    auth = HTTPBasicAuth(email, api_token)
    headers = {'Content-Type': 'application/json', 'Accept': 'application/json'}

    get_resp = requests.get(get_url, auth=auth, headers=headers, timeout=30)

    if not get_resp.ok:
        logger.error(json.dumps({
            'step': 'confluence_get_error',
            'status_code': get_resp.status_code,
            'body': get_resp.text[:300],
        }))
        return _resp(502, {'error': 'Failed to update Confluence'})

    page_data = get_resp.json()
    page_body = page_data.get('body', {}).get('storage', {}).get('value', '')
    page_title = page_data.get('title', '')
    version_number = page_data.get('version', {}).get('number', 0)

    logger.info(json.dumps({
        'step': 'confluence_get',
        'result': 'ok',
        'page_id': source_page_id,
        'version': version_number,
    }))

    # ── Step 4: Find matching incomplete task and mark it complete ───────────
    updated_body, changed = _replace_task(page_body, item_text)

    if not changed:
        # Task not found or already complete — treat as success (idempotent)
        logger.info(json.dumps({'step': 'task_match', 'result': 'not_found_or_already_complete'}))

    # ── Step 5: PUT updated page back to Confluence ──────────────────────────
    put_url = f'https://{site_url}/wiki/api/v2/pages/{source_page_id}'
    put_payload = {
        'id': source_page_id,
        'status': 'current',
        'title': page_title,
        'body': {'representation': 'storage', 'value': updated_body},
        'version': {'number': version_number + 1, 'message': 'Marked complete via Action Items Dashboard'},
    }
    logger.info(json.dumps({'step': 'confluence_put', 'url': put_url, 'version': version_number + 1}))

    put_resp = requests.put(put_url, json=put_payload, auth=auth, headers=headers, timeout=30)

    if not put_resp.ok:
        logger.error(json.dumps({
            'step': 'confluence_put_error',
            'status_code': put_resp.status_code,
            'body': put_resp.text[:300],
        }))
        return _resp(502, {'error': 'Failed to update Confluence'})

    logger.info(json.dumps({'step': 'confluence_put', 'result': 'ok', 'status_code': put_resp.status_code}))

    # ── Step 6: Update DynamoDB item status to "complete" ───────────────────
    logger.info(json.dumps({'step': 'dynamodb_update', 'item_id': item_id}))

    try:
        table.update_item(
            Key={'item_id': item_id},
            UpdateExpression='SET #s = :s',
            ExpressionAttributeNames={'#s': 'status'},
            ExpressionAttributeValues={':s': 'complete'},
        )
    except ClientError as exc:
        logger.error(json.dumps({'step': 'dynamodb_update_error', 'error': str(exc)}))
        return _resp(500, {'error': 'Internal server error'})

    logger.info(json.dumps({'step': 'dynamodb_update', 'result': 'ok', 'item_id': item_id}))

    return _resp(200, {'success': True, 'item_id': item_id})


def _replace_task(body, item_text):
    """Find the first incomplete <ac:task> whose body matches item_text and
    replace its status with 'complete'. Returns (updated_body, changed_bool)."""
    changed = False

    def _replacer(match):
        nonlocal changed
        block = match.group(1)
        status_m = _TASK_STATUS_RE.search(block)
        body_m = _TASK_BODY_RE.search(block)

        if not status_m or not body_m:
            return block

        status = status_m.group(1).strip()
        if status != 'incomplete':
            return block

        task_body_html = body_m.group(1)
        plain = _strip_html(task_body_html).strip()

        if plain == item_text.strip():
            changed = True
            return block.replace(
                '<ac:task-status>incomplete</ac:task-status>',
                '<ac:task-status>complete</ac:task-status>',
                1,
            )
        return block

    updated = _TASK_BLOCK_RE.sub(_replacer, body)
    return updated, changed


def _resp(status_code, body_dict):
    return {
        'statusCode': status_code,
        'body': json.dumps(body_dict),
        'headers': {'Content-Type': 'application/json'},
    }
