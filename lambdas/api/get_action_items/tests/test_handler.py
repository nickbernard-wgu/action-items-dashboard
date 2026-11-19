import json
import os
import pytest
import boto3
from decimal import Decimal
from unittest.mock import patch, MagicMock
from botocore.exceptions import ClientError

# Set TABLE_NAME and region before importing the handler
os.environ.setdefault("TABLE_NAME", "action-items-test")
os.environ.setdefault("AWS_DEFAULT_REGION", "us-east-1")
os.environ.setdefault("AWS_ACCESS_KEY_ID", "test")
os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "test")

import moto

TABLE_NAME = "action-items-test"


def _make_table(dynamodb):
    table = dynamodb.create_table(
        TableName=TABLE_NAME,
        KeySchema=[{"AttributeName": "item_id", "KeyType": "HASH"}],
        AttributeDefinitions=[
            {"AttributeName": "item_id", "AttributeType": "S"},
            {"AttributeName": "status", "AttributeType": "S"},
        ],
        GlobalSecondaryIndexes=[
            {
                "IndexName": "status-index",
                "KeySchema": [{"AttributeName": "status", "KeyType": "HASH"}],
                "Projection": {"ProjectionType": "ALL"},
            }
        ],
        BillingMode="PAY_PER_REQUEST",
    )
    table.meta.client.get_waiter("table_exists").wait(TableName=TABLE_NAME)
    return table


# ---------------------------------------------------------------------------
# Test 1: Empty table returns items=[] and last_synced=null
# ---------------------------------------------------------------------------
@moto.mock_aws
def test_empty_table_returns_empty_items():
    os.environ["TABLE_NAME"] = TABLE_NAME
    dynamodb = boto3.resource("dynamodb", region_name="us-east-1")
    _make_table(dynamodb)

    from lambdas.api.get_action_items import handler  # noqa: F401
    import importlib
    import lambdas.api.get_action_items.handler as h
    importlib.reload(h)

    result = h.lambda_handler({}, None)
    assert result["statusCode"] == 200
    body = json.loads(result["body"])
    assert body["items"] == []
    assert body["last_synced"] is None


# ---------------------------------------------------------------------------
# Test 2: Seeded open items are returned with correct last_synced
# ---------------------------------------------------------------------------
@moto.mock_aws
def test_open_items_returned_with_last_synced():
    os.environ["TABLE_NAME"] = TABLE_NAME
    dynamodb = boto3.resource("dynamodb", region_name="us-east-1")
    table = _make_table(dynamodb)

    table.put_item(Item={
        "item_id": "item-001",
        "status": "open",
        "text": "Do the thing",
        "last_synced": "2024-01-15T10:00:00",
    })
    table.put_item(Item={
        "item_id": "item-002",
        "status": "open",
        "text": "Do another thing",
        "last_synced": "2024-01-20T12:00:00",
    })

    import importlib
    import lambdas.api.get_action_items.handler as h
    importlib.reload(h)

    result = h.lambda_handler({}, None)
    assert result["statusCode"] == 200
    body = json.loads(result["body"])
    assert len(body["items"]) == 2
    ids = {item["item_id"] for item in body["items"]}
    assert ids == {"item-001", "item-002"}
    # most recent last_synced
    assert body["last_synced"] == "2024-01-20T12:00:00"


# ---------------------------------------------------------------------------
# Test 3: _sync_meta sentinel is excluded even when status=open
# ---------------------------------------------------------------------------
@moto.mock_aws
def test_sync_meta_sentinel_excluded():
    os.environ["TABLE_NAME"] = TABLE_NAME
    dynamodb = boto3.resource("dynamodb", region_name="us-east-1")
    table = _make_table(dynamodb)

    table.put_item(Item={
        "item_id": "_sync_meta",
        "status": "open",
        "text": "sentinel record",
    })
    table.put_item(Item={
        "item_id": "item-real",
        "status": "open",
        "text": "real item",
    })

    import importlib
    import lambdas.api.get_action_items.handler as h
    importlib.reload(h)

    result = h.lambda_handler({}, None)
    assert result["statusCode"] == 200
    body = json.loads(result["body"])
    ids = [item["item_id"] for item in body["items"]]
    assert "_sync_meta" not in ids
    assert "item-real" in ids


# ---------------------------------------------------------------------------
# Test 4: DynamoDB ClientError returns 500 without exposing exception message
# ---------------------------------------------------------------------------
def test_dynamodb_client_error_returns_500():
    os.environ["TABLE_NAME"] = TABLE_NAME

    import importlib
    import lambdas.api.get_action_items.handler as h
    importlib.reload(h)

    error_response = {"Error": {"Code": "InternalServerError", "Message": "boom"}}
    client_error = ClientError(error_response, "Query")

    mock_table = MagicMock()
    mock_table.query.side_effect = client_error

    mock_dynamodb = MagicMock()
    mock_dynamodb.Table.return_value = mock_table

    with patch("boto3.resource", return_value=mock_dynamodb):
        result = h.lambda_handler({}, None)

    assert result["statusCode"] == 500
    body = json.loads(result["body"])
    assert body == {"error": "Internal server error"}
    assert "boom" not in result["body"]
    assert "InternalServerError" not in result["body"]


# ---------------------------------------------------------------------------
# last_synced comes from the _sync_meta record, even when no items are open
# ---------------------------------------------------------------------------
@moto.mock_aws
def test_last_synced_comes_from_sync_meta_when_no_open_items():
    os.environ["TABLE_NAME"] = TABLE_NAME
    dynamodb = boto3.resource("dynamodb", region_name="us-east-1")
    table = _make_table(dynamodb)
    table.put_item(Item={"item_id": "_sync_meta", "last_synced": "2026-11-18T12:00:00Z"})
    table.put_item(Item={"item_id": "done-1", "status": "complete", "last_synced": "2026-11-01T00:00:00Z"})

    import importlib
    import lambdas.api.get_action_items.handler as h
    importlib.reload(h)
    body = json.loads(h.lambda_handler({}, None)["body"])
    assert body["items"] == []
    assert body["last_synced"] == "2026-11-18T12:00:00Z"
