#!/usr/bin/env python3
"""Read-only snapshot helper for approved public LoteDiretor sources.

It captures raw metadata responses with timestamp, headers, SHA-256 and a
manifest. It does not bypass authentication, follow private links, or infer
permission from technical reachability.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path

USER_AGENT="LoteDiretor-Ingestion/0.1 (+https://github.com/paulohspred/Lotediretor)"
CONFIG=Path("data/connectors/priority.json")
OUT=Path("data/snapshots")


def now():
    return datetime.now(timezone.utc).isoformat()


def fetch(url, timeout=60):
    p=urllib.parse.urlparse(url)
    if p.scheme not in {"http","https"} or not p.netloc:
        raise ValueError("only public HTTP(S) URLs are supported")
    req=urllib.request.Request(url,headers={"User-Agent":USER_AGENT})
    with urllib.request.urlopen(req,timeout=timeout) as r:
        return r.read(), dict(r.headers.items()), r.geturl(), getattr(r,"status",None)


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def json_url(url):
    p=urllib.parse.urlparse(url)
    q=urllib.parse.parse_qs(p.query)
    q["f"]=["pjson"]
    return urllib.parse.urlunparse(p._replace(query=urllib.parse.urlencode(q,doseq=True)))


def wfs_url(url):
    p=urllib.parse.urlparse(url)
    q=urllib.parse.parse_qs(p.query)
    q.update({"service":["WFS"],"request":["GetCapabilities"],"version":["2.0.0"]})
    return urllib.parse.urlunparse(p._replace(query=urllib.parse.urlencode(q,doseq=True)))


def ckan_url(base):
    return base.rstrip("/")+"/api/3/action/package_search?rows=1000"


class Links(HTMLParser):
    def __init__(self):
        super().__init__(); self.links=[]
    def handle_starttag(self,tag,attrs):
        if tag.lower()=="a":
            href=dict(attrs).get("href")
            if href: self.links.append(href)


def directory_index(url,body):
    root=urllib.parse.urlparse(url)
    parser=Links(); parser.feed(body.decode("utf-8",errors="replace"))
    out=[]
    for href in parser.links:
        absolute=urllib.parse.urljoin(url,href)
        p=urllib.parse.urlparse(absolute)
        if (p.scheme,p.netloc)!=(root.scheme,root.netloc):
            continue
        if href in {"../","./","/"}: continue
        out.append({"href":href,"url":absolute,"directory":p.path.endswith("/")})
    return out


def choose_url(item):
    kind=item["kind"]; url=item["url"]
    if kind=="arcgis_service": return json_url(url)
    if kind=="wfs_capabilities": return wfs_url(url)
    if kind=="ckan_catalog": return ckan_url(url)
    return url


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("connector_id")
    ap.add_argument("--out",type=Path,default=OUT)
    args=ap.parse_args()

    cfg=json.loads(CONFIG.read_text(encoding="utf-8"))
    item=next((x for x in cfg["connectors"] if x["id"]==args.connector_id),None)
    if not item:
        raise SystemExit("unknown connector")
    if not item.get("approved"):
        raise SystemExit("connector is not approved")

    target=choose_url(item)
    body,headers,final_url,status=fetch(target)

    stamp=datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    folder=args.out/item["id"]/stamp
    folder.mkdir(parents=True,exist_ok=False)

    ext=".bin"
    ctype=(headers.get("Content-Type") or "").lower()
    if "json" in ctype or item["kind"] in {"arcgis_service","ckan_catalog","json_api","frictionless_datapackage"}:
        ext=".json"
    elif "xml" in ctype or item["kind"]=="wfs_capabilities":
        ext=".xml"
    elif "html" in ctype or item["kind"]=="public_directory":
        ext=".html"

    raw=folder/f"raw{ext}"
    raw.write_bytes(body)

    extra={}
    if item["kind"]=="public_directory":
        extra["entries"]=directory_index(final_url,body)
        (folder/"index.json").write_text(json.dumps(extra,ensure_ascii=False,indent=2),encoding="utf-8")

    manifest={
        "schema_version":"0.1.0",
        "connector_id":item["id"],
        "source_id":item["source_id"],
        "kind":item["kind"],
        "requested_url":target,
        "final_url":final_url,
        "http_status":status,
        "captured_at":now(),
        "content_type":headers.get("Content-Type"),
        "content_length":len(body),
        "sha256":sha256(body),
        "headers":{
            k:v for k,v in headers.items()
            if k.lower() in {"content-type","content-length","etag","last-modified","cache-control"}
        },
        "raw_file":raw.name,
        "mode":item.get("mode"),
        "notes":item.get("notes")
    }
    (folder/"manifest.json").write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(manifest,ensure_ascii=False,indent=2))


if __name__=="__main__":
    main()
