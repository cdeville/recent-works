#!/usr/bin/env python3

import argparse
from datetime import datetime, UTC
import tzlocal

"""
EXAMPLES:

# Run without arguments to return current UTC time
$ ./utc_time.py
16-Jul-2025 19:29 UTC

# Paste time from AWS Alerts to convert to local timezone
$ ./utc_time.py --convert "16-Jul-2025 19:06 UTC"
16-Jul-2025 14:06 CDT-0500
"""

# Return current UTC time in "AWS" format
def get_current_utc_time():
    return datetime.now(UTC).strftime('%d-%b-%Y %H:%M UTC')

# Convert "AWS" formatted UTC time to local timezone
def convert_utc_to_local(timestr: str):
    try:
        # Parse input time string (e.g., "16 Jul 2025 19:06:50 UTC")
        utc_time = datetime.strptime(timestr, "%d-%b-%Y %H:%M %Z")

        # Set UTC timezone explicitly
        utc_time = utc_time.replace(tzinfo=UTC)

        # Convert to local timezone
        local_tz = tzlocal.get_localzone()
        local_time = utc_time.astimezone(local_tz)

        return local_time.strftime('%d-%b-%Y %H:%M %Z%z')
    except ValueError:
        return "Invalid time format. Use: '16-Jul-2025 19:06:50 UTC'"

def main():
    parser = argparse.ArgumentParser(description="UTC time utility")
    parser.add_argument(
        "--convert",
        metavar='"16 Jul 2025 19:06:50 UTC"',
        help="Convert given UTC time string to local timezone"
    )
    args = parser.parse_args()

    if args.convert:
        print(convert_utc_to_local(args.convert))
    else:
        print(get_current_utc_time())

if __name__ == "__main__":
    main()
