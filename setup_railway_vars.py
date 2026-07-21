"""
One-off script to set Railway environment variables via the Railway CLI.
Requires: railway CLI installed (npm i -g @railway/cli) and logged in (railway login).

Usage:
    python setup_railway_vars.py

It will prompt for each variable and run `railway variables set` for you.
"""

import subprocess
import sys


VARIABLES = [
    ("API_ID", "Telegram API ID (from my.telegram.org)"),
    ("API_HASH", "Telegram API hash (from my.telegram.org)"),
    ("SESSION_STRING", "Pre-generated Telethon session string"),
    ("SOURCE_GROUP_ID", "Numeric ID of the source group"),
    ("BOT_TOKEN", "Bot token (from @BotFather)"),
    ("DEST_GROUP_ID", "Numeric ID of the destination group"),
]


def main():
    print("Railway Environment Variable Setup")
    print("=" * 40)
    print("Enter each value when prompted.\n")

    env_pairs = []
    for name, desc in VARIABLES:
        value = input(f"{name} ({desc}): ").strip()
        if not value:
            print(f"  Skipping {name} (empty)")
            continue
        env_pairs.append(f"{name}={value}")

    if not env_pairs:
        print("\nNo variables to set. Exiting.")
        return

    cmd = ["railway", "variables", "set"] + env_pairs
    print(f"\nRunning: railway variables set ...")
    result = subprocess.run(cmd, capture_output=True, text=True)

    if result.returncode == 0:
        print("Done! Variables set successfully.")
        if result.stdout:
            print(result.stdout)
    else:
        print(f"Failed (exit code {result.returncode})")
        if result.stderr:
            print(result.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
