import json
import os
import logging
from decimal import Decimal

import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger()
logger.setLevel(logging.INFO)


class DecimalEncoder(json.JSONEncoder):
    """Serialize Decimal values as floats for JSON output."""

    def default(self, obj):
        if isinstance(obj, Decimal):
            return float(obj)
        return super().default(obj)


def lambda_handler(event, context):
    logger.info(json.dumps({"event": event}))

    table_name = os.environ["TABLE_NAME"]
    region = os.environ.get("AWS_DEFAULT_REGION", os.environ.get("AWS_REGION", "us-east-1"))
    dynamodb = boto3.resource("dynamodb", region_name=region)
    table = dynamodb.Table(table_name)

    try:
        items = []
        query_kwargs = {
            "IndexName": "status-index",
            "KeyConditionExpression": boto3.dynamodb.conditions.Key("status").eq("open"),
        }

        while True:
            response = table.query(**query_kwargs)
            items.extend(response.get("Items", []))
            last_key = response.get("LastEvaluatedKey")
            if not last_key:
                break
            query_kwargs["ExclusiveStartKey"] = last_key

    except ClientError as exc:
        logger.error(json.dumps({"error": str(exc)}))
        return {
            "statusCode": 500,
            "body": json.dumps({"error": "Internal server error"}),
            "headers": {"Content-Type": "application/json"},
        }

    # Exclude sentinel items whose item_id starts with "_"
    filtered = [item for item in items if not item.get("item_id", "").startswith("_")]

    # Determine last_synced: most recent ISO datetime across all items
    last_synced = None
    for item in filtered:
        val = item.get("last_synced")
        if val is not None:
            str_val = str(val)
            if last_synced is None or str_val > last_synced:
                last_synced = str_val

    return {
        "statusCode": 200,
        "body": json.dumps(
            {"items": filtered, "last_synced": last_synced},
            cls=DecimalEncoder,
        ),
        "headers": {"Content-Type": "application/json"},
    }
