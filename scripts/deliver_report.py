#!/usr/bin/env python3
"""
Report Delivery Script
Bypasses OpenClaw CLI to send HTML reports directly via Telegram Bot API
"""

import requests
import sys
import argparse
from pathlib import Path
from datetime import datetime

def send_document(bot_token, chat_id, file_path, caption=None):
    """Send a file as a document via Telegram Bot API"""
    url = f"https://api.telegram.org/bot{bot_token}/sendDocument"
    data = {"chat_id": chat_id}
    if caption:
        data["caption"] = caption

    try:
        with open(file_path, "rb") as f:
            files = {
                "document": (Path(file_path).name, f, "text/html")
            }
            r = requests.post(url, data=data, files=files, timeout=60)
            r.raise_for_status()
            return r.json()
    except Exception as e:
        print(f"❌ Delivery failed: {e}")
        return None

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--file", required=True, help="Path to the HTML report")
    parser.add_argument("--caption", default=None, help="Caption for the document")
    args = parser.parse_args()

    BOT_TOKEN = "8714788498:AAGOboi7Fu3V1eRD6PFQjXMqpTI3p2ErVLc"
    CHAT_ID = "-4872065090" # Trading Sandbox

    print(f"🚀 Delivering report: {args.file}...")
    result = send_document(BOT_TOKEN, CHAT_ID, args.file, args.caption)
    
    if result:
        print("✅ Report successfully delivered to Trading Sandbox.")
    else:
        sys.exit(1)
