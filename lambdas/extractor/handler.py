"""
Action Items extractor Lambda.

Fetches action items from Confluence meeting-notes pages and writes
open items to DynamoDB. Uses an incremental version cache stored in
the _sync_meta DynamoDB item to skip pages that haven't changed.
"""

import boto3
from botocore.exceptions import ClientError
import concurrent.futures
import hashlib
import json as _json
import json
import logging
import os
import uuid
from datetime import datetime

from confluence_client import ConfluenceClient
from text_processing import (
    canonical_owner,
    extract_owner,
    extract_date_from_title,
    age_bucket,
    compute_item_age,
    extract_tasks_from_body,
)

# ─── Structured logging ──────────────────────────────────────────────────────

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)


def _log(event: str, **kwargs):
    log.info(_json.dumps({"event": event, **kwargs}))


# ─── Constants ───────────────────────────────────────────────────────────────

MEETING_NOTES_PARENT_ID = "198967351"
SPACE = "DEVEX"
TABLE_NAME = os.environ.get("DYNAMODB_TABLE", "action-items")
MAX_WORKERS = 6
_EXCLUDED_PAGES = frozenset(["action items dashboard", "template"])

# ─── Credentials cache ───────────────────────────────────────────────────────

_credentials_cache = None


def get_credentials() -> dict:
    global _credentials_cache
    if _credentials_cache is None:
        client = boto3.client("secretsmanager")
        resp = client.get_secret_value(
            SecretId="action-items-dashboard/confluence-credentials"
        )
        _credentials_cache = json.loads(resp["SecretString"])
    return _credentials_cache


# ─── Helpers ─────────────────────────────────────────────────────────────────


def is_excluded_page(title: str) -> bool:
    """Case-insensitive substring match against the excluded-title fragments."""
    lowered = title.lower()
    return any(fragment in lowered for fragment in _EXCLUDED_PAGES)


def should_skip_page(cached_versions: dict, page_id: str, current_version: int) -> bool:
    return cached_versions.get(str(page_id)) == current_version


def derive_item_id(source_page_id: str, normalized_text: str) -> str:
    normalized_hash = hashlib.sha256(normalized_text.encode()).hexdigest()
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"{source_page_id}:{normalized_hash}"))


# ─── Handler ─────────────────────────────────────────────────────────────────


def handler(event, context):
    creds = get_credentials()
    site_url = creds["site_url"]
    email = creds["username"]
    api_token = creds["api_token"]

    confluence = ConfluenceClient(
        site=site_url,
        email=email,
        api_token=api_token,
        max_workers=MAX_WORKERS,
    )

    dynamo = boto3.resource("dynamodb")
    table = dynamo.Table(TABLE_NAME)

    # ── Load version cache from _sync_meta ───────────────────────────────────
    cached_versions: dict = {}
    try:
        resp = table.get_item(Key={"item_id": "_sync_meta"})
        item = resp.get("Item", {})
        raw = item.get("page_versions", "{}")
        cached_versions = json.loads(raw)
    except Exception as e:
        _log("sync_meta_load_error", error=str(e))

    # ── Fetch child pages ─────────────────────────────────────────────────────
    children = confluence.fetch_children_with_versions(MEETING_NOTES_PARENT_ID)

    pages_checked = 0
    pages_changed = 0
    items_written = 0

    # Identify pages that need fetching (changed or new)
    changed_pages = []
    for child in children:
        page_id = child["id"]
        title = child["title"]
        version = child["version"]

        if is_excluded_page(title):
            _log("page_processed", page_id=page_id, title=title, items_written=0, skipped=True)
            continue

        pages_checked += 1

        if should_skip_page(cached_versions, page_id, version):
            _log("page_processed", page_id=page_id, title=title, items_written=0, skipped=True)
            continue

        changed_pages.append(child)

    # ── Parallel body fetch ───────────────────────────────────────────────────
    def fetch_body(child):
        page_id = child["id"]
        try:
            body, fetched_title, fetched_version = confluence.get_page_body(page_id)
            return page_id, fetched_title, fetched_version, body, None
        except Exception as e:
            return page_id, child["title"], child["version"], None, e

    fetched = {}
    if changed_pages:
        with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            futures = {executor.submit(fetch_body, ch): ch for ch in changed_pages}
            for future in concurrent.futures.as_completed(futures):
                page_id, title, version, body, err = future.result()
                fetched[page_id] = {
                    "title": title,
                    "version": version,
                    "body": body,
                    "error": err,
                }

    # ── Process changed pages ─────────────────────────────────────────────────
    updated_versions = dict(cached_versions)

    for child in changed_pages:
        page_id = child["id"]
        info = fetched.get(page_id, {})
        title = info.get("title", child["title"])
        version = info.get("version", child["version"])
        body = info.get("body")
        err = info.get("error")

        if err or body is None:
            _log("page_fetch_error", page_id=page_id, title=title, error=str(err))
            continue

        pages_changed += 1

        tasks = extract_tasks_from_body(body, page_title=title)
        date_created_iso = extract_date_from_title(title)
        page_items_written = 0

        source_url = f"https://{site_url}/wiki/spaces/{SPACE}/pages/{page_id}"

        for task in tasks:
            if task["status"] != "incomplete":
                continue

            text = task["text"]
            owner = canonical_owner(extract_owner(text))
            secondary_owners = task["secondary_owners"]
            priority = task["priority"]
            due_date = task["due_date"]
            blocked_by = task["blocked_by"]

            item_id = derive_item_id(page_id, text)
            age = age_bucket(compute_item_age(date_created_iso)) if date_created_iso else "unknown"

            item = {
                "item_id": item_id,
                "status": "open",
                "text": text,
                "owner": owner,
                "secondary_owners": secondary_owners,
                "priority": priority or "",
                "due_date": due_date or "",
                "blocked_by": blocked_by or "",
                "source_page_id": page_id,
                "source_meeting_title": title,
                "source_meeting_url": source_url,
                "date_created_iso": date_created_iso,
                "age_bucket": age,
                "last_synced": datetime.utcnow().isoformat() + "Z",
            }

            try:
                # Never overwrite an item the dashboard already marked complete
                table.put_item(
                    Item=item,
                    ConditionExpression="attribute_not_exists(item_id) OR #st <> :done",
                    ExpressionAttributeNames={"#st": "status"},
                    ExpressionAttributeValues={":done": "complete"},
                )
                page_items_written += 1
                items_written += 1
            except ClientError as e:
                if e.response["Error"]["Code"] == "ConditionalCheckFailedException":
                    _log("item_already_complete", item_id=item_id)
                else:
                    _log("dynamo_write_error", item_id=item_id, error=str(e))
            except Exception as e:
                _log("dynamo_write_error", item_id=item_id, error=str(e))

        updated_versions[str(page_id)] = version
        _log(
            "page_processed",
            page_id=page_id,
            title=title,
            items_written=page_items_written,
            skipped=False,
        )

    # ── Persist updated version cache ─────────────────────────────────────────
    try:
        table.put_item(Item={
            "item_id": "_sync_meta",
            "page_versions": json.dumps(updated_versions),
            "last_synced": datetime.utcnow().isoformat() + "Z",
        })
    except Exception as e:
        _log("sync_meta_write_error", error=str(e))

    _log(
        "sync_complete",
        pages_checked=pages_checked,
        pages_changed=pages_changed,
        items_written=items_written,
    )

    return {
        "statusCode": 200,
        "body": json.dumps({
            "pages_changed": pages_changed,
            "items_written": items_written,
        }),
    }
