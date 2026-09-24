#!/usr/bin/env python3
"""Generate safe search queries for public-source discovery.

This tool only prints queries. It does not execute searches.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

DEFAULT_PLAYBOOK = Path("data/source-registry/search-playbook.json")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--playbook", type=Path, default=DEFAULT_PLAYBOOK)
    parser.add_argument("--domain", required=True)
    parser.add_argument("--legislative-domain")
    parser.add_argument("--registry-domain")
    parser.add_argument("--category")
    args = parser.parse_args()

    data = json.loads(args.playbook.read_text(encoding="utf-8"))
    values = {
        "domain": args.domain,
        "legislative_domain": args.legislative_domain or args.domain,
        "registry_domain": args.registry_domain or args.domain,
    }

    for item in data["query_templates"]:
        if args.category and item["category"] != args.category:
            continue
        print(f"# {item['id']} [{item['category']}]")
        print(item["query"].format(**values))
        print()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
