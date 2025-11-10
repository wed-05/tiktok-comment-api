thonimport csv
import json
import os
from typing import Any, Dict, Iterable, List, Optional

from ..extractors.utils_parser import ensure_directory_for_file

class ExportManager:
    """
    Handles exporting scraped comment data to various formats such as JSON and CSV.
    """

    def __init__(self, logger) -> None:
        self.logger = logger

    def export(
        self,
        comments: List[Dict[str, Any]],
        output_dir: str,
        base_filename: str,
        export_format: str = "json",
    ) -> None:
        export_format = export_format.lower()
        if export_format not in {"json", "csv", "both"}:
            self.logger.warning(
                f"Unknown export_format '{export_format}', falling back to 'json'."
            )
            export_format = "json"

        os.makedirs(output_dir, exist_ok=True)

        if export_format in {"json", "both"}:
            json_path = os.path.join(output_dir, f"{base_filename}.json")
            self._export_json(comments, json_path)

        if export_format in {"csv", "both"}:
            csv_path = os.path.join(output_dir, f"{base_filename}.csv")
            self._export_csv(comments, csv_path)

    def _export_json(self, comments: List[Dict[str, Any]], path: str) -> None:
        ensure_directory_for_file(path)
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(comments, f, ensure_ascii=False, indent=4)
            self.logger.info(f"Exported {len(comments)} comment(s) to JSON: {path}")
        except OSError as exc:
            self.logger.error(f"Failed to write JSON file {path}: {exc}")

    def _export_csv(self, comments: List[Dict[str, Any]], path: str) -> None:
        ensure_directory_for_file(path)
        if not comments:
            self.logger.warning(
                f"No comments to export to CSV. Creating an empty file at: {path}"
            )

        # Determine CSV headers
        headers = self._determine_headers(comments)

        try:
            with open(path, "w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=headers)
                writer.writeheader()
                for comment in comments:
                    flat_row = self._flatten_comment(comment, headers)
                    writer.writerow(flat_row)
            self.logger.info(f"Exported {len(comments)} comment(s) to CSV: {path}")
        except OSError as exc:
            self.logger.error(f"Failed to write CSV file {path}: {exc}")

    def _determine_headers(self, comments: List[Dict[str, Any]]) -> List[str]:
        # Basic union of top-level keys
        keys = set()
        for comment in comments:
            keys.update(comment.keys())

        # Ensure consistent ordering for important keys
        preferred_order = [
            "aweme_id",
            "cid",
            "author_pin",
            "comment_language",
            "create_time",
            "digg_count",
            "reply_comment_total",
            "region",
            "text",
            "text_extra",
            "user",
            "share_info",
        ]

        ordered: List[str] = []
        for key in preferred_order:
            if key in keys:
                ordered.append(key)
                keys.remove(key)
        ordered.extend(sorted(keys))
        return ordered

    def _flatten_comment(
        self, comment: Dict[str, Any], headers: Iterable[str]
    ) -> Dict[str, Any]:
        """
        Flatten nested dictionaries into JSON strings for CSV export.
        """
        row: Dict[str, Any] = {}
        for key in headers:
            value: Optional[Any] = comment.get(key)
            if isinstance(value, (dict, list)):
                row[key] = json.dumps(value, ensure_ascii=False)
            elif value is None:
                row[key] = ""
            else:
                row[key] = value
        return row