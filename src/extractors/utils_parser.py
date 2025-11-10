thonimport logging
import os
import re
from typing import Any, Dict, Iterable, Optional
from urllib.parse import urlparse, parse_qs

logger = logging.getLogger("tiktok_comment_scraper.utils")

def parse_tiktok_url(url: str) -> str:
    """
    Extract the TikTok video ID from a variety of common URL formats.

    Supported patterns include:
    - https://www.tiktok.com/@user/video/7211250685902359850
    - https://www.tiktok.com/t/ZT8abc123/
    - https://vm.tiktok.com/ZT8abc123/
    - URLs where the aweme_id appears as a query parameter.
    """
    if not url:
        raise ValueError("Empty URL provided")

    parsed = urlparse(url)
    if not parsed.scheme or not parsed.netloc:
        raise ValueError(f"Invalid TikTok URL: {url}")

    # First, try to find a numeric ID in the path
    path_segments = [segment for segment in parsed.path.split("/") if segment]
    numeric_id_pattern = re.compile(r"(\d{6,})")

    for segment in reversed(path_segments):
        match = numeric_id_pattern.search(segment)
        if match:
            video_id = match.group(1)
            logger.debug(f"Extracted video ID '{video_id}' from URL path.")
            return video_id

    # Fallback: look for aweme_id or similar in query parameters
    query_params = parse_qs(parsed.query or "")
    for key in ("aweme_id", "video_id", "item_id"):
        if key in query_params and query_params[key]:
            candidate = query_params[key][0]
            if numeric_id_pattern.fullmatch(candidate):
                logger.debug(
                    f"Extracted video ID '{candidate}' from query parameter '{key}'."
                )
                return candidate

    raise ValueError(f"Could not locate TikTok video ID in URL: {url}")

def build_comment_api_url(
    video_id: str, cursor: int = 0, count: int = 20
) -> str:
    """
    Construct a TikTok comment API URL.

    Note: TikTok's internal APIs are not documented and may change at any time.
    This function uses a commonly observed pattern. In real usage this may need
    to be adapted to current network traffic patterns.
    """
    base_url = "https://www.tiktok.com/api/comment/list/"
    return (
        f"{base_url}?aid=1988&cursor={cursor}&count={count}"
        f"&aweme_id={video_id}"
    )

def ensure_directory_for_file(path: str) -> None:
    """
    Ensure that the directory for a file path exists.
    """
    directory = os.path.dirname(os.path.abspath(path))
    if directory and not os.path.exists(directory):
        os.makedirs(directory, exist_ok=True)

def nested_get(
    data: Dict[str, Any],
    keys: Iterable[str],
    default: Optional[Any] = None,
) -> Any:
    """
    Safely retrieve nested values from a dictionary using a list of keys.
    """
    current: Any = data
    for key in keys:
        if not isinstance(current, dict):
            return default
        if key not in current:
            return default
        current = current[key]
    return current

def normalize_text_whitespace(text: Optional[str]) -> Optional[str]:
    """
    Collapse excessive whitespace in a text field.
    """
    if text is None:
        return None
    return re.sub(r"\s+", " ", text).strip()