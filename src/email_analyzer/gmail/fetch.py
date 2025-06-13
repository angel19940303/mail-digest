"""Fetch Gmail messages within a rolling time window."""

from __future__ import annotations

import base64
import re
from dataclasses import dataclass, field
from datetime import datetime
from email.utils import parsedate_to_datetime
from typing import Any

import html2text
from bs4 import BeautifulSoup

from email_analyzer.config import AppConfig
from email_analyzer.gmail.auth import build_gmail_service


@dataclass
class EmailMessage:
    message_id: str
    thread_id: str
    internal_date_ms: int
    from_addr: str
    from_email: str
    subject: str
    date_header: str
    snippet: str
    labels: list[str] = field(default_factory=list)
    body_text: str = ""
    category: str | None = None

    @property
    def internal_datetime(self) -> datetime:
        return datetime.fromtimestamp(self.internal_date_ms / 1000.0).astimezone()


_EMAIL_RE = re.compile(r"<([^>]+)>|([^\s<>]+@[^\s<>]+)")


def parse_email_address(from_header: str) -> tuple[str, str]:
    """Return (display/from string, normalized email)."""
    raw = from_header or ""
    match = _EMAIL_RE.search(raw)
    addr = (match.group(1) or match.group(2) or "").strip().lower()
    return raw.strip(), addr


def _header_value(headers: list[dict[str, str]], name: str) -> str:
    for h in headers:
        if h.get("name", "").lower() == name.lower():
            return h.get("value", "")
    return ""


def _decode_body(data: str) -> str:
    return base64.urlsafe_b64decode(data.encode("utf-8")).decode("utf-8", errors="replace")


def _html_to_text(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style"]):
        tag.decompose()
    text = html2text.HTML2Text()
    text.ignore_links = False
    text.body_width = 0
    return text.handle(str(soup)).strip()


def _extract_body(payload: dict[str, Any]) -> str:
    mime = payload.get("mimeType", "")
    body_data = payload.get("body", {}).get("data")
    if body_data:
        decoded = _decode_body(body_data)
        if mime == "text/html":
            return _html_to_text(decoded)
        return decoded

    parts = payload.get("parts") or []
    plain = ""
    html = ""
    for part in parts:
        part_mime = part.get("mimeType", "")
        if part_mime.startswith("multipart/"):
            nested = _extract_body(part)
            if nested:
                return nested
        part_data = part.get("body", {}).get("data")
        if not part_data:
            continue
        decoded = _decode_body(part_data)
        if part_mime == "text/plain" and not plain:
            plain = decoded
        elif part_mime == "text/html" and not html:
            html = decoded
    if plain:
        return plain.strip()
    if html:
        return _html_to_text(html)
    return ""


def _parse_message_list_item(item: dict[str, Any], detail: dict[str, Any]) -> EmailMessage:
    headers = detail.get("payload", {}).get("headers", [])
    from_raw = _header_value(headers, "From")
    from_display, from_email = parse_email_address(from_raw)
    subject = _header_value(headers, "Subject")
    date_header = _header_value(headers, "Date")
    snippet = detail.get("snippet", "")
    body = _extract_body(detail.get("payload", {}))
    internal_ms = int(detail.get("internalDate", item.get("internalDate", 0)))

    return EmailMessage(
        message_id=item["id"],
        thread_id=item.get("threadId", detail.get("threadId", "")),
        internal_date_ms=internal_ms,
        from_addr=from_display,
        from_email=from_email,
        subject=subject,
        date_header=date_header,
        snippet=snippet,
        labels=detail.get("labelIds", []),
        body_text=body,
    )


def list_message_ids(service, query: str) -> list[dict[str, Any]]:
    messages: list[dict[str, Any]] = []
    page_token = None
    while True:
        kwargs: dict[str, Any] = {"userId": "me", "q": query, "maxResults": 100}
        if page_token:
            kwargs["pageToken"] = page_token
        resp = service.users().messages().list(**kwargs).execute()
        messages.extend(resp.get("messages", []))
        page_token = resp.get("nextPageToken")
        if not page_token:
            break
    return messages


def fetch_messages_in_window(
    config: AppConfig,
    window_start: datetime,
    window_end: datetime,
    *,
    interactive: bool = True,
) -> list[EmailMessage]:
    service = build_gmail_service(config, interactive=interactive)
    start_ms = int(window_start.timestamp() * 1000)
    end_ms = int(window_end.timestamp() * 1000)

    raw_items = list_message_ids(service, config.gmail.broad_query)
    results: list[EmailMessage] = []

    for item in raw_items:
        meta = (
            service.users()
            .messages()
            .get(userId="me", id=item["id"], format="metadata", metadataHeaders=[])
            .execute()
        )
        internal_ms = int(meta.get("internalDate", 0))
        if internal_ms < start_ms or internal_ms >= end_ms:
            continue

        detail = (
            service.users()
            .messages()
            .get(userId="me", id=item["id"], format="full")
            .execute()
        )
        results.append(_parse_message_list_item(item, detail))

    results.sort(key=lambda m: m.internal_date_ms)
    return results


def download_raw_eml(service, message_id: str) -> bytes:
    raw = (
        service.users()
        .messages()
        .get(userId="me", id=message_id, format="raw")
        .execute()
    )
    data = raw.get("raw", "")
    return base64.urlsafe_b64decode(data.encode("utf-8"))


def format_date_header(date_header: str) -> str:
    if not date_header:
        return ""
    try:
        return parsedate_to_datetime(date_header).isoformat()
    except (TypeError, ValueError, OverflowError):
        return date_header
