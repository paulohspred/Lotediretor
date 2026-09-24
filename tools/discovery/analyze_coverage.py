#!/usr/bin/env python3
"""Build a coverage report from data/source-registry/bootstrap.json."""
from __future__ import annotations
import json
from collections import Counter, defaultdict
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
REG=ROOT/"data/source-registry/bootstrap.json"
OUT=ROOT/"data/source-registry/coverage-report.json"

UF_BY_PREFIX={
"11":"RO","12":"AC","13":"AM","14":"RR","15":"PA","16":"AP","17":"TO",
"21":"MA","22":"PI","23":"CE","24":"RN","25":"PB","26":"PE","27":"AL","28":"SE","29":"BA",
"31":"MG","32":"ES","33":"RJ","35":"SP","41":"PR","42":"SC","43":"RS","50":"MS","51":"MT","52":"GO","53":"DF"}
UFS=["AC","AL","AP","AM","BA","CE","DF","ES","GO","MA","MT","MS","MG","PA","PB","PR","PE","PI","RJ","RN","RS","RO","RR","SC","SP","SE","TO"]
KEY_DOMAINS=["cadastre","lots","buildings","iptu","itbi","plan_director","zoning","urban_planning","building_permits","licensing","habite_se","imagery","terrain","risk","environment","heritage","official_gazette"]

def main():
    data=json.loads(REG.read_text(encoding="utf-8"))
    state={uf:{"sources":0,"municipalities":set(),"domains":set(),"source_ids":[]} for uf in UFS}
    municipalities={}
    domain_counts=Counter()

    for s in data["sources"]:
        code=str(s.get("municipality_ibge",""))
        uf=s.get("uf") or (UF_BY_PREFIX.get(code[:2]) if len(code)>=2 else None)
        if uf in state:
            state[uf]["sources"]+=1
            state[uf]["source_ids"].append(s["id"])
            if code:
                state[uf]["municipalities"].add(code)
            state[uf]["domains"].update(s.get("domain",[]))
        if code:
            m=municipalities.setdefault(code,{"ibge":code,"uf":uf,"source_ids":[],"domains":set()})
            m["source_ids"].append(s["id"])
            m["domains"].update(s.get("domain",[]))
        domain_counts.update(s.get("domain",[]))

    by_uf={}
    for uf,v in state.items():
        by_uf[uf]={
            "sources":v["sources"],
            "municipalities":len(v["municipalities"]),
            "key_domains_present":[d for d in KEY_DOMAINS if d in v["domains"]],
            "key_domains_missing":[d for d in KEY_DOMAINS if d not in v["domains"]],
            "source_ids":sorted(v["source_ids"]),
        }

    muni_out=[]
    for code,m in municipalities.items():
        muni_out.append({
            "ibge":code,"uf":m["uf"],"source_count":len(m["source_ids"]),
            "source_ids":sorted(m["source_ids"]),"domains":sorted(m["domains"])
        })
    muni_out.sort(key=lambda x:((x["uf"] or ""),x["ibge"]))

    report={
        "schema_version":"0.1.0",
        "as_of":data.get("generated_at") or "2026-09-24",
        "source_count":len(data["sources"]),
        "municipality_count":len(muni_out),
        "key_domains":KEY_DOMAINS,
        "coverage_by_uf":by_uf,
        "municipalities":muni_out,
        "domain_counts":dict(domain_counts.most_common()),
    }
    OUT.write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({"source_count":report["source_count"],"municipality_count":report["municipality_count"],"output":str(OUT)},ensure_ascii=False))

if __name__=="__main__":
    main()
