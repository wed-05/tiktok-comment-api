thonimport json
import logging
import time
from typing import Any, Dict, List, Optional

import requests

from .utils_parser import (
    build_comment_api_url,
    nested_get,
    normalize_text_whitespace,
    parse_tiktok_url,
)

class TikTokCommentScraper:
    """
    High-level scraper that retrieves comments for a given TikTok video URL.

    This implementation relies on TikTok's public web API endpoints. Since these
    endpoints may change at any time, the scraper is designed to fail gracefully,
    returning an empty list and logging a clear error if parsing fails.
    """

    def __init__(
        self,
        max_comments: int = 100,
        scrape_replies: bool = True,
        timeout: int = 10,
        delay: float = 0.75,
        user_agent: str = (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/122.0 Safari/537.36"
        ),
        logger: Optional[logging.Logger] = None,
    ) -> None:
        self.max_comments = max(1, int(max_comments))
        self.scrape_replies = bool(scrape_replies)
        self.timeout = max(1, int(timeout))
        self.delay = max(0.0, float(delay))
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": user_agent,
                "Accept": "application/json, text/plain, */*",
                "Accept-Language": "en-US,en;q=0.9",
            }
        )
        self.logger = logger or logging.getLogger("tiktok_comment_scraper")

    def fetch_comments_for_url(self, url: str) -> List[Dict[str, Any]]:
        """
        Retrieve and normalize comments for a TikTok video URL.
        """
        try:
            video_id = parse_tiktok_url(url)
        except ValueError as exc:
            self.logger.error(f"URL parsing failed: {exc}")
            return []

        comments: List[Dict[str, Any]] = []
        cursor = 0
        has_more = True

        self.logger.info(
            f"Fetching comments for video_id={video_id} "
            f"(max_comments={self.max_comments})"
        )

        while has_more and len(comments) < self.max_comments:
            batch = self._fetch_comment_page(video_id, cursor)
            if batch is None:
                # Network or parsing error; stop early
                break

            page_comments, has_more, next_cursor = batch
            normalized = [self._normalize_comment(c, video_id) for c in page_comments]
            comments.extend(normalized)

            self.logger.debug(
                f"Fetched {len(page_comments)} raw comments "
                f"(total normalized so far: {len(comments)})"
            )

            cursor = next_cursor
            if has_more and len(comments) < self.max_comments:
                time.sleep(self.delay)

        # Trim to max_comments
        if len(comments) > self.max_comments:
            comments = comments[: self.max_comments]

        self.logger.info(
            f"Finished fetching comments for {video_id}: {len(comments)} item(s)."
        )
        return comments

    def _fetch_comment_page(
        self, video_id: str, cursor: int
    ) -> Optional[tuple]:
        """
        Fetch a single page of comments.

        Returns a tuple: (comments_list, has_more, next_cursor)
        or None on error.
        """
        url = build_comment_api_url(video_id=video_id, cursor=cursor, count=20)
        self.logger.debug(f"Requesting comments page: {url}")

        try:
            response = self.session.get(url, timeout=self.timeout)
        except requests.RequestException as exc:
            self.logger.error(f"Network error while requesting TikTok API: {exc}")
            return None

        if response.status_code != 200:
            self.logger.error(
                f"TikTok API returned non-200 status code: {response.status_code}"
            )
            return None

        try:
            payload = response.json()
        except json.JSONDecodeError as exc:
            self.logger.error(f"Failed to decode TikTok API JSON response: {exc}")
            return None

        # TikTok often nests data differently depending on endpoint.
        # We support a couple of common patterns.
        comments = payload.get("comments")
        if comments is None:
            comments = nested_get(payload, ["data", "comments"], default=[])

        if not isinstance(comments, list):
            self.logger.error("Unexpected comment payload structure.")
            return None

        has_more = bool(
            payload.get("has_more")
            or nested_get(payload, ["data", "has_more"], default=False)
        )
        next_cursor = int(
            payload.get("cursor")
            or nested_get(payload, ["data", "cursor"], default=0)
            or 0
        )

        return comments, has_more, next_cursor

    def _normalize_comment(
        self, raw_comment: Dict[str, Any], video_id: str
    ) -> Dict[str, Any]:
        """
        Convert a raw TikTok comment object into the structured format
        described in the project README.
        """
        text = raw_comment.get("text")
        text = normalize_text_whitespace(text) if text is not None else None

        user_raw = raw_comment.get("user") or raw_comment.get("user_info") or {}
        share_raw = raw_comment.get("share_info") or {}

        normalized = {
            "author_pin": bool(raw_comment.get("author_pin", False)),
            "aweme_id": str(raw_comment.get("aweme_id") or video_id),
            "cid": str(raw_comment.get("cid") or raw_comment.get("id") or ""),
            "comment_language": raw_comment.get("comment_language")
            or raw_comment.get("lang")
            or None,
            "create_time": int(raw_comment.get("create_time") or 0),
            "digg_count": int(raw_comment.get("digg_count") or 0),
            "reply_comment_total": int(
                raw_comment.get("reply_comment_total")
                or raw_comment.get("reply_count")
                or 0
            ),
            "text": text,
            "text_extra": raw_comment.get("text_extra") or [],
            "region": raw_comment.get("region")
            or user_raw.get("region")
            or user_raw.get("country")
            or None,
            "user": {
                "nickname": user_raw.get("nickname") or user_raw.get("name"),
                "unique_id": user_raw.get("unique_id")
                or user_raw.get("username")
                or user_raw.get("id"),
                "signature": user_raw.get("signature") or user_raw.get("bio"),
                "ins_id": user_raw.get("ins_id")
                or user_raw.get("instagram_id")
                or None,
            },
            "share_info": {
                "desc": share_raw.get("desc")
                or share_raw.get("description")
                or None,
                "url": share_raw.get("url") or None,
            },
        }

        # If we aren't scraping replies, we can choose to ignore nested replies in raw_comment.
        # Currently, replies are not attached; however, the hook is here for extension.
        if self.scrape_replies and raw_comment.get("reply_comment"):
            # In a more advanced version, you'd recursively normalize nested comments here.
            self.logger.debug(
                "Reply scraping is enabled, but nested reply normalization "
                "is not implemented in this reference scraper."
            )

        return normalized