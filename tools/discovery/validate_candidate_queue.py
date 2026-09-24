#!/usr/bin/env python3
"""Validate the candidate discovery queue."""
from __future__ import annotations
import json
import sys
from pathlib import Path
from urllib.parse import urlparse

PATH = Path("data/source-registry/candidate-queue.json")
REQUIRED = {"id","status","category","authority","url","discovered_via","goal","risks","next_checks"}

def main() -> int:
    data=json.loads(PATH.read_text(encoding="utf-8"))
    statuses=set(data["statuses"])
    seen=set()
    errors=[]
    for i,c in enumerate(data["candidates"]):
        p=f"candidate[{i}]({c.get('id','?')})"
        missing=sorted(k for k in REQUIRED if c.get(k) in (None,"",[]))
        if missing:
            errors.append(f"{p}: missing {', '.join(missing)}")
        if c.get("id") in seen:
            errors.append(f"{p}: duplicate id")
        seen.add(c.get("id"))
        if c.get("status") not in statuses:
            errors.append(f"{p}: invalid status")
        u=urlparse(str(c.get("url","")))
        if u.scheme not in {"http","https"} or not u.netloc:
            errors.append(f"{p}: invalid url")
    print(json.dumps({"ok":not errors,"candidates":len(data["candidates"]),"errors":errors},ensure_ascii=False))
    return 1 if errors else 0

if __name__=="__main__":
    raise SystemExit(main())
