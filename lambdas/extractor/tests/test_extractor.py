"""Unit tests for the extractor Lambda."""

from lambdas.extractor.text_processing import extract_tasks_from_body


def test_extraction_shape():
    body = (
        '<ac:task>'
        '<ac:task-id>1</ac:task-id>'
        '<ac:task-status>incomplete</ac:task-status>'
        '<ac:task-body>@Nick Bernard - Review the Port.io docs by 7/14</ac:task-body>'
        '</ac:task>'
    )
    tasks = extract_tasks_from_body(body, page_title="7.1.2026 - Team Sync")
    assert len(tasks) == 1
    t = tasks[0]
    assert t["status"] == "incomplete"
    assert "Nick Bernard" in t["text"] or "Port.io" in t["text"]
    from lambdas.extractor.text_processing import extract_owner
    assert extract_owner(t["text"]) == "Nick Bernard"


def test_incremental_skip():
    from lambdas.extractor.handler import should_skip_page

    cached = {"page_123": 5}
    assert should_skip_page(cached, "page_123", 5) is True
    assert should_skip_page(cached, "page_123", 6) is False
    assert should_skip_page(cached, "page_999", 1) is False


def test_item_id_stability():
    from lambdas.extractor.handler import derive_item_id

    id1 = derive_item_id("123456", "Review the Port.io docs")
    id2 = derive_item_id("123456", "Review the Port.io docs")
    assert id1 == id2
    id3 = derive_item_id("123456", "Different text")
    assert id1 != id3


def test_get_credentials_calls_secrets_manager():
    import json
    from unittest.mock import MagicMock, patch

    import lambdas.extractor.handler as h

    h._credentials_cache = None  # reset cache

    mock_client = MagicMock()
    mock_client.get_secret_value.return_value = {
        'SecretString': json.dumps({
            'username': 'test@wgu.edu',
            'api_token': 'token123',
            'site_url': 'wgu.atlassian.net',
        })
    }

    with patch('boto3.client', return_value=mock_client):
        creds = h.get_credentials()

    mock_client.get_secret_value.assert_called_once_with(
        SecretId='action-items-dashboard/confluence-credentials'
    )
    assert 'username' in creds
    assert 'api_token' in creds
    assert 'site_url' in creds


def test_excluded_page_titles_match_by_substring():
    from lambdas.extractor.handler import is_excluded_page
    assert is_excluded_page("Open Action Items Dashboard")
    assert is_excluded_page("Action Items Dashboard - Archived")
    assert is_excluded_page("11.3.2026 - TPM Working Group Template Review")
    assert not is_excluded_page("10.15.2026 - IDKit Team Sprint Planning")


def test_put_item_never_overwrites_completed_item():
    import os

    import boto3
    from moto import mock_aws
    with mock_aws():
        os.environ.setdefault("AWS_DEFAULT_REGION", "us-east-1")
        os.environ.setdefault("AWS_ACCESS_KEY_ID", "test")
        os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "test")
        ddb = boto3.resource("dynamodb", region_name="us-east-1")
        table = ddb.create_table(
            TableName="t",
            KeySchema=[{"AttributeName": "item_id", "KeyType": "HASH"}],
            AttributeDefinitions=[{"AttributeName": "item_id", "AttributeType": "S"}],
            BillingMode="PAY_PER_REQUEST",
        )
        from botocore.exceptions import ClientError
        cond = dict(
            ConditionExpression="attribute_not_exists(item_id) OR #st <> :done",
            ExpressionAttributeNames={"#st": "status"},
            ExpressionAttributeValues={":done": "complete"},
        )
        table.put_item(Item={"item_id": "x", "status": "complete"})
        try:
            table.put_item(Item={"item_id": "x", "status": "open"}, **cond)
            raised = False
        except ClientError as e:
            raised = e.response["Error"]["Code"] == "ConditionalCheckFailedException"
        assert raised
        assert table.get_item(Key={"item_id": "x"})["Item"]["status"] == "complete"
