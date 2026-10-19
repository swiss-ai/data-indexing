#!/usr/bin/env python3
"""Mint an API key for the Apertus Data Search query endpoint.

Prints the key once (give it to the consumer) and the JSON entry to add to the
Secret. Only the hash is ever stored, so a key that is lost cannot be recovered
— issue a replacement and delete the old entry.

    python3 make_api_key.py alice-cli
    python3 make_api_key.py eval-pipeline --expires 2027-01-01
"""

import argparse
import hashlib
import json
import secrets
import sys

# Identifies the key's purpose at a glance if it ever turns up in a log or a
# pasted command, and makes it greppable in secret-scanning tools.
PREFIX = "aps"


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("name", help="who or what this key is for, e.g. alice-cli")
    p.add_argument("--expires", metavar="YYYY-MM-DD",
                   help="optional expiry date; the key stops working after it")
    args = p.parse_args()

    key = f"{PREFIX}_{secrets.token_urlsafe(32)}"
    entry = {"name": args.name, "hash": hashlib.sha256(key.encode()).hexdigest()}
    if args.expires:
        entry["expires"] = args.expires

    print("Key (shown once — send it to the consumer over a private channel):")
    print(f"\n    {key}\n")
    print("Add this entry to the 'keys' list in the Secret:")
    print(f"\n{json.dumps(entry, indent=2)}\n")
    print("Then apply the Secret. Pods pick up the change within ~1 minute; no redeploy needed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
