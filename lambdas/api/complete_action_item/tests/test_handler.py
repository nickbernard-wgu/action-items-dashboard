import json
import os
import pytest
from unittest.mock import patch, MagicMock, call

# Set env vars before importing the handler
os.environ.setdefault('TABLE_NAME', 'action-items-test')
os.environ.setdefault('SECRET_NAME', 'action-items-dashboard/confluence-credentials')
os.environ.setdefault('AWS_DEFAULT_REGION', 'us-east-1')
os.environ.setdefault('AWS_ACCESS_KEY_ID', 'test')
os.environ.setdefault('AWS_SECRET_ACCESS_KEY', 'test')

import lambdas.api.complete_action_item.handler as h


# ── Helpers ──────────────────────────────────────────────────────────────────

def _event(item_id='abc-123'):
    return {'pathParameters': {'id': item_id}}


def _make_item(item_id='abc-123', text='Do the thing', source_page_id='9999'):
    return {'item_id': item_id, 'text': text, 'source_page_id': source_page_id, 'status': 'open'}


def _page_body(text='Do the thing', status='incomplete'):
    return (
        f'<ac:task>'
        f'<ac:task-id>1</ac:task-id>'
        f'<ac:task-status>{status}</ac:task-status>'
        f'<ac:task-body>{text}</ac:task-body>'
        f'</ac:task>'
    )


def _mock_secrets():
    return json.dumps({
        'api_token': 'tok',
        'email': 'user@example.com',
        'site_url': 'example.atlassian.net',
    })


def _make_get_resp(text='Do the thing', status='incomplete'):
    mock_resp = MagicMock()
    mock_resp.ok = True
    mock_resp.json.return_value = {
        'title': 'Meeting Page',
        'body': {'storage': {'value': _page_body(text, status)}},
        'version': {'number': 5},
    }
    return mock_resp


def _make_put_resp(ok=True, status_code=200):
    mock_resp = MagicMock()
    mock_resp.ok = ok
    mock_resp.status_code = status_code
    mock_resp.text = 'error detail' if not ok else ''
    return mock_resp


# ── Test 1: Item not found → 404, no Confluence calls ────────────────────────

@patch('lambdas.api.complete_action_item.handler.requests.put')
@patch('lambdas.api.complete_action_item.handler.requests.get')
@patch('lambdas.api.complete_action_item.handler.boto3.client')
@patch('lambdas.api.complete_action_item.handler.boto3.resource')
def test_item_not_found_returns_404_no_confluence(
    mock_resource, mock_client, mock_requests_get, mock_requests_put
):
    mock_table = MagicMock()
    mock_table.get_item.return_value = {}           # no 'Item' key → not found
    mock_resource.return_value.Table.return_value = mock_table

    result = h.lambda_handler(_event('missing-id'), None)

    assert result['statusCode'] == 404
    body = json.loads(result['body'])
    assert body == {'error': 'Item not found'}

    mock_requests_get.assert_not_called()
    mock_requests_put.assert_not_called()


# ── Test 2: Happy path → DynamoDB UpdateItem called, HTTP 200 ────────────────

@patch('lambdas.api.complete_action_item.handler.requests.put')
@patch('lambdas.api.complete_action_item.handler.requests.get')
@patch('lambdas.api.complete_action_item.handler.boto3.client')
@patch('lambdas.api.complete_action_item.handler.boto3.resource')
def test_happy_path_updates_dynamodb_and_returns_200(
    mock_resource, mock_client, mock_requests_get, mock_requests_put
):
    item = _make_item()

    mock_table = MagicMock()
    mock_table.get_item.return_value = {'Item': item}
    mock_resource.return_value.Table.return_value = mock_table

    mock_secrets_client = MagicMock()
    mock_secrets_client.get_secret_value.return_value = {'SecretString': _mock_secrets()}
    mock_client.return_value = mock_secrets_client

    mock_requests_get.return_value = _make_get_resp(text=item['text'])
    mock_requests_put.return_value = _make_put_resp(ok=True, status_code=200)

    result = h.lambda_handler(_event(item['item_id']), None)

    assert result['statusCode'] == 200
    body = json.loads(result['body'])
    assert body == {'success': True, 'item_id': item['item_id']}

    # DynamoDB UpdateItem was called with status='complete'
    mock_table.update_item.assert_called_once()
    call_kwargs = mock_table.update_item.call_args[1]
    assert call_kwargs['ExpressionAttributeValues'][':s'] == 'complete'


# ── Test 3: Confluence PUT non-2xx → no DynamoDB update, HTTP 502 ────────────

@patch('lambdas.api.complete_action_item.handler.requests.put')
@patch('lambdas.api.complete_action_item.handler.requests.get')
@patch('lambdas.api.complete_action_item.handler.boto3.client')
@patch('lambdas.api.complete_action_item.handler.boto3.resource')
def test_confluence_put_failure_returns_502_no_dynamodb_update(
    mock_resource, mock_client, mock_requests_get, mock_requests_put
):
    item = _make_item()

    mock_table = MagicMock()
    mock_table.get_item.return_value = {'Item': item}
    mock_resource.return_value.Table.return_value = mock_table

    mock_secrets_client = MagicMock()
    mock_secrets_client.get_secret_value.return_value = {'SecretString': _mock_secrets()}
    mock_client.return_value = mock_secrets_client

    mock_requests_get.return_value = _make_get_resp(text=item['text'])
    mock_requests_put.return_value = _make_put_resp(ok=False, status_code=400)

    result = h.lambda_handler(_event(item['item_id']), None)

    assert result['statusCode'] == 502
    body = json.loads(result['body'])
    assert body == {'error': 'Failed to update Confluence'}

    mock_table.update_item.assert_not_called()


# ── Test 4: Secrets Manager called with correct SecretId on happy path ────────

@patch('lambdas.api.complete_action_item.handler.requests.put')
@patch('lambdas.api.complete_action_item.handler.requests.get')
@patch('lambdas.api.complete_action_item.handler.boto3.client')
@patch('lambdas.api.complete_action_item.handler.boto3.resource')
def test_secrets_manager_called_with_correct_secret_id(
    mock_resource, mock_client, mock_requests_get, mock_requests_put
):
    item = _make_item()

    mock_table = MagicMock()
    mock_table.get_item.return_value = {'Item': item}
    mock_resource.return_value.Table.return_value = mock_table

    mock_secrets_client = MagicMock()
    mock_secrets_client.get_secret_value.return_value = {'SecretString': _mock_secrets()}
    mock_client.return_value = mock_secrets_client

    mock_requests_get.return_value = _make_get_resp(text=item['text'])
    mock_requests_put.return_value = _make_put_resp(ok=True, status_code=200)

    h.lambda_handler(_event(item['item_id']), None)

    mock_secrets_client.get_secret_value.assert_called_once_with(
        SecretId='action-items-dashboard/confluence-credentials'
    )
