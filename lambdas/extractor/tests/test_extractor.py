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
    from unittest.mock import patch, MagicMock
    import json
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
