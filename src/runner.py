thonimport argparse
import json
import logging
import os
import sys
from typing import Any, Dict, List, Optional

# Ensure the src directory is on the Python path so we can import local packages
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
if CURRENT_DIR not in sys.path:
    sys.path.insert(0, CURRENT_DIR)

from extractors.tiktok_parser import TikTokCommentScraper  # type: ignore
from outputs.export_manager import ExportManager  # type: ignore

def setup_logger(verbosity: int) -> logging.Logger:
    level = logging.WARNING
    if verbosity == 1:
        level = logging.INFO
    elif verbosity >= 2:
        level = logging.DEBUG

    logger = logging.getLogger("tiktok_comment_scraper")
    logger.setLevel(level)

    if not logger.handlers:
        handler = logging.StreamHandler()
        formatter = logging.Formatter(
            "[%(asctime)s] [%(levelname)s] %(message)s", "%Y-%m-%d %H:%M:%S"
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)

    return logger

def load_json_file(path: str, logger: logging.Logger) -> Any:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        logger.error(f"File not found: {path}")
        raise
    except json.JSONDecodeError as exc:
        logger.error(f"Failed to parse JSON file {path}: {exc}")
        raise

def resolve_default_paths() -> Dict[str, str]:
    """
    Compute default paths based on the repository layout:

    TikTok Comment API/
      src/
      data/
    """
    src_dir = CURRENT_DIR
    project_root = os.path.dirname(src_dir)
    return {
        "project_root": project_root,
        "data_dir": os.path.join(project_root, "data"),
        "default_inputs": os.path.join(project_root, "data", "inputs.sample.json"),
        "default_settings": os.path.join(src_dir, "config", "settings.example.json"),
    }

def apply_job_overrides(
    base_settings: Dict[str, Any], job: Dict[str, Any]
) -> Dict[str, Any]:
    merged = base_settings.copy()
    # Simple overrides only for known fields
    for key in ("max_comments", "scrape_replies", "export_format"):
        if key in job:
            merged[key] = job[key]
    return merged

def run_job(
    job: Dict[str, Any],
    settings: Dict[str, Any],
    export_manager: ExportManager,
    output_dir: str,
    logger: logging.Logger,
    index: int,
    cli_export_format: Optional[str] = None,
) -> None:
    video_url = job.get("video_url") or job.get("url")
    if not video_url:
        logger.error(f"Job #{index + 1} is missing 'video_url' field.")
        return

    job_settings = apply_job_overrides(settings, job)

    max_comments = int(job_settings.get("max_comments", 100))
    scrape_replies = bool(job_settings.get("scrape_replies", True))
    timeout = int(job_settings.get("request_timeout", 10))
    delay = float(job_settings.get("delay_between_requests", 0.75))
    user_agent = str(
        job_settings.get(
            "user_agent",
            "Mozilla/5.0 (compatible; TikTokCommentScraper/1.0; +https://bitbash.dev)",
        )
    )

    # Determine export format: CLI flag > job > settings default
    export_format = (
        cli_export_format
        or job.get("export_format")
        or job_settings.get("export_format")
        or "json"
    )

    output_basename = str(
        job.get("output_file") or f"tiktok_comments_{index + 1}"
    )

    logger.info(
        f"Starting job #{index + 1} for URL={video_url} "
        f"(max_comments={max_comments}, scrape_replies={scrape_replies}, "
        f"format={export_format})"
    )

    scraper = TikTokCommentScraper(
        max_comments=max_comments,
        scrape_replies=scrape_replies,
        timeout=timeout,
        delay=delay,
        user_agent=user_agent,
        logger=logger,
    )

    comments = scraper.fetch_comments_for_url(video_url)
    if not comments:
        logger.warning(
            f"No comments retrieved for job #{index + 1}. "
            "This may be due to network issues or TikTok API changes."
        )
    else:
        logger.info(
            f"Job #{index + 1}: Retrieved {len(comments)} comment(s) "
            f"for export."
        )

    export_manager.export(
        comments=comments,
        output_dir=output_dir,
        base_filename=output_basename,
        export_format=export_format,
    )

    logger.info(f"Completed job #{index + 1}")

def main() -> None:
    paths = resolve_default_paths()

    parser = argparse.ArgumentParser(
        description="TikTok Comment API Scraper - CLI Runner"
    )
    parser.add_argument(
        "--input",
        "-i",
        dest="input_path",
        default=paths["default_inputs"],
        help="Path to the JSON file with scraping jobs "
        f"(default: {paths['default_inputs']})",
    )
    parser.add_argument(
        "--settings",
        "-s",
        dest="settings_path",
        default=paths["default_settings"],
        help="Path to the settings JSON file "
        f"(default: {paths['default_settings']})",
    )
    parser.add_argument(
        "--output-dir",
        "-o",
        dest="output_dir",
        default=paths["data_dir"],
        help=f"Directory where results will be stored (default: {paths['data_dir']})",
    )
    parser.add_argument(
        "--export-format",
        "-f",
        dest="export_format",
        choices=["json", "csv", "both"],
        help="Override export format for all jobs (json, csv, both). "
        "If omitted, falls back to job/settings.",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="count",
        default=0,
        help="Increase logging verbosity (use -v or -vv).",
    )

    args = parser.parse_args()
    logger = setup_logger(args.verbose)

    logger.debug(f"Resolved paths: {paths}")

    settings = load_json_file(args.settings_path, logger)
    jobs = load_json_file(args.input_path, logger)

    if not isinstance(jobs, list):
        logger.error(
            f"Input file {args.input_path} is expected to contain a list of jobs."
        )
        sys.exit(1)

    export_manager = ExportManager(logger=logger)

    os.makedirs(args.output_dir, exist_ok=True)

    for idx, job in enumerate(jobs):
        if not isinstance(job, dict):
            logger.warning(f"Skipping job #{idx + 1}: Not a JSON object.")
            continue
        run_job(
            job=job,
            settings=settings,
            export_manager=export_manager,
            output_dir=args.output_dir,
            logger=logger,
            index=idx,
            cli_export_format=args.export_format,
        )

if __name__ == "__main__":
    main()