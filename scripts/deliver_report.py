#!/usr/bin/env python3
"""
Report Delivery Script
Delivers HTML reports directly via Telegram Bot API
"""

import argparse
import logging
import os
import sys
import time
from functools import wraps
from pathlib import Path
from typing import Any, Dict, Optional

import requests
from dotenv import load_dotenv
from requests.exceptions import HTTPError, RequestException, Timeout

# Load environment variables from .env file (if it exists)
from traderlib.paths import project_root

PROJECT_ROOT = project_root()
load_dotenv(PROJECT_ROOT / '.env')

# Exit codes
EXIT_SUCCESS = 0
EXIT_FILE_NOT_FOUND = 1
EXIT_AUTH_FAILED = 2
EXIT_NETWORK_ERROR = 3
EXIT_API_ERROR = 4
EXIT_CONFIG_ERROR = 5


def retry(max_attempts: int = 3, backoff: int = 2):
    """Decorator for exponential backoff retry logic."""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            for attempt in range(max_attempts):
                try:
                    return func(*args, **kwargs)
                except (Timeout, RequestException) as e:
                    if attempt == max_attempts - 1:
                        raise
                    wait = backoff ** attempt
                    logging.warning(f"Attempt {attempt + 1} failed: {e}. Retrying in {wait}s...")
                    time.sleep(wait)
        return wrapper
    return decorator


class TelegramReporter:
    """Handles delivery of reports via Telegram Bot API."""

    def __init__(self, bot_token: str, chat_id: str, timeout: int = 60):
        """
        Initialize Telegram reporter.

        Args:
            bot_token: Telegram bot token from @BotFather
            chat_id: Target chat ID (channel or group)
            timeout: Request timeout in seconds

        Raises:
            ValueError: If bot_token or chat_id is empty
        """
        if not bot_token:
            raise ValueError("Bot token cannot be empty")
        if not chat_id:
            raise ValueError("Chat ID cannot be empty")

        self.bot_token = bot_token
        self.chat_id = chat_id
        self.timeout = timeout
        self.base_url = f"https://api.telegram.org/bot{bot_token}"

    @retry(max_attempts=3)
    def send_document(
        self,
        file_path: Path,
        caption: Optional[str] = None,
        dry_run: bool = False
    ) -> Optional[Dict[str, Any]]:
        """
        Send a file as a document via Telegram Bot API.

        Args:
            file_path: Path to the file to send
            caption: Optional caption text
            dry_run: If True, simulate without actually sending

        Returns:
            API response dict on success, None on failure

        Raises:
            FileNotFoundError: If file_path doesn't exist
            requests.exceptions.Timeout: On network timeout
            requests.exceptions.HTTPError: On API errors
        """
        url = f"{self.base_url}/sendDocument"
        data = {"chat_id": self.chat_id}
        if caption:
            data["caption"] = caption

        if dry_run:
            logging.info(f"[DRY RUN] Would send: {file_path.name} to {self.chat_id}")
            logging.info(f"[DRY RUN] Caption: {caption or '(none)'}")
            return {"ok": True, "result": {"message_id": 0, "dry_run": True}}

        try:
            with open(file_path, "rb") as f:
                files = {"document": (file_path.name, f, "text/html")}
                logging.debug(f"Sending POST to {url}")
                r = requests.post(url, data=data, files=files, timeout=self.timeout)
                r.raise_for_status()
                response = r.json()
                logging.info(f"Message sent successfully (ID: {response.get('result', {}).get('message_id', 'unknown')})")
                return response

        except HTTPError as e:
            status_code = e.response.status_code if hasattr(e.response, 'status_code') else 'unknown'
            if status_code == 401:
                logging.error("Authentication failed: Invalid bot token")
                raise
            elif status_code == 400:
                logging.error(f"Bad request: {e.response.text if hasattr(e.response, 'text') else e}")
                raise
            elif status_code == 403:
                logging.error("Forbidden: Bot may not have access to this chat")
                raise
            elif status_code == 429:
                logging.error("Rate limited by Telegram API")
                raise
            else:
                logging.error(f"HTTP {status_code}: {e}")
                raise
        except Timeout:
            logging.error(f"Request timed out after {self.timeout}s")
            raise
        except RequestException as e:
            logging.error(f"Network error: {e}")
            raise


def validate_file(file_path: str) -> Path:
    """
    Validate that file exists and is readable.

    Args:
        file_path: String path to validate

    Returns:
        Path object

    Raises:
        FileNotFoundError: If file doesn't exist
        ValueError: If path is not a file
    """
    path = Path(file_path)

    if not path.exists():
        raise FileNotFoundError(f"File not found: {path}")

    if not path.is_file():
        raise ValueError(f"Not a file: {path}")

    if not os.access(path, os.R_OK):
        raise PermissionError(f"Cannot read file: {path}")

    # Warn if not HTML
    if path.suffix.lower() != '.html':
        logging.warning(f"Expected .html file, got: {path.suffix}")

    logging.debug(f"File validated: {path.absolute()}")
    return path


def load_config() -> Dict[str, str]:
    """
    Load configuration from environment variables.

    Returns:
        Dict with 'bot_token' and 'chat_id'

    Raises:
        ValueError: If TELEGRAM_BOT_TOKEN is not set
    """
    bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "-4872065090")  # Default to Trading Sandbox

    if not bot_token:
        raise ValueError(
            "TELEGRAM_BOT_TOKEN not set.\n"
            "Export it: export TELEGRAM_BOT_TOKEN=your_token\n"
            "Or create a .env file (see .env.example)"
        )

    return {"bot_token": bot_token, "chat_id": chat_id}


def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Deliver HTML reports via Telegram Bot API",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Basic delivery
  python3 deliver_report.py --file reports/premarket_report.html

  # With caption
  python3 deliver_report.py --file report.html --caption "Morning briefing"

  # Test without sending (dry run)
  python3 deliver_report.py --file report.html --dry-run

  # Send to different chat
  python3 deliver_report.py --file report.html --chat-id -1001234567890

  # Verbose output
  python3 deliver_report.py --file report.html --verbose
        """
    )

    parser.add_argument(
        "--file",
        required=True,
        help="Path to the HTML report file"
    )
    parser.add_argument(
        "--caption",
        default=None,
        help="Caption text for the document"
    )
    parser.add_argument(
        "--chat-id",
        default=os.getenv("TELEGRAM_CHAT_ID", "-4872065090"),
        help="Target chat ID (default: -4872065090 Trading Sandbox, or from TELEGRAM_CHAT_ID env var)"
    )
    parser.add_argument(
        "--bot-token",
        default=os.getenv("TELEGRAM_BOT_TOKEN"),
        help="Bot token (or use TELEGRAM_BOT_TOKEN env var)"
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=60,
        help="Request timeout in seconds (default: 60)"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Simulate without actually sending the message"
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable verbose (debug) output"
    )

    return parser.parse_args()


def main() -> int:
    """Main entry point."""
    args = parse_args()

    # Setup logging
    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=log_level,
        format='%(asctime)s - %(levelname)s - %(message)s',
        datefmt='%H:%M:%S'
    )
    logger = logging.getLogger(__name__)

    logger.info(f"🚀 Report delivery starting")

    # Validate file first
    try:
        file_path = validate_file(args.file)
        logger.info(f"File validated: {file_path.name}")
    except FileNotFoundError as e:
        logger.error(f"❌ {e}")
        return EXIT_FILE_NOT_FOUND
    except (ValueError, PermissionError) as e:
        logger.error(f"❌ {e}")
        return EXIT_FILE_NOT_FOUND

    # Get credentials
    bot_token = args.bot_token or os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = args.chat_id

    if not bot_token:
        logger.error(
            "❌ TELEGRAM_BOT_TOKEN not set.\n"
            "Export it: export TELEGRAM_BOT_TOKEN=your_token\n"
            "Or use --bot-token flag"
        )
        return EXIT_CONFIG_ERROR

    logger.debug(f"Target chat: {chat_id}")
    logger.debug(f"Timeout: {args.timeout}s")

    # Initialize reporter
    try:
        reporter = TelegramReporter(bot_token, chat_id, timeout=args.timeout)
    except ValueError as e:
        logger.error(f"❌ Configuration error: {e}")
        return EXIT_CONFIG_ERROR

    # Send the report
    try:
        if args.dry_run:
            logger.info("🔍 DRY RUN MODE — No actual message will be sent")

        result = reporter.send_document(
            file_path,
            caption=args.caption,
            dry_run=args.dry_run
        )

        if result:
            if args.dry_run:
                logger.info("✅ Dry run successful — message would be delivered")
            else:
                logger.info(f"✅ Report delivered successfully to Trading Sandbox")
            return EXIT_SUCCESS
        else:
            logger.error("❌ Delivery failed: No response from API")
            return EXIT_API_ERROR

    except HTTPError:
        return EXIT_AUTH_FAILED if '401' in str(sys.exc_info()) else EXIT_API_ERROR
    except (Timeout, RequestException):
        return EXIT_NETWORK_ERROR
    except Exception as e:
        logger.error(f"❌ Unexpected error: {e}")
        return EXIT_API_ERROR


if __name__ == "__main__":
    sys.exit(main())
