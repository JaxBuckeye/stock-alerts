"""Live check against the real SEC site, run on a dev machine (the SEC blocks GitHub runners):
    TICKER=CYCN python -m tests.live_cvr
"""
import json
import os
import sys
import time

from app import cvr

sym = os.environ.get("TICKER", "CYCN").strip().upper()
t0 = time.time()
info = cvr.discover(sym)
print(json.dumps(info, indent=2)[:20000])
print(f"\nLookup took {time.time() - t0:.0f}s")
print("assets:", info.get("assets"))
print("companies:", info.get("companies"))
print("obligor:", info.get("obligor"))
print("search queries:", [q for q, _ in cvr.search_queries(dict(info, sym=sym))])
print("news queries:", [q for q, _ in cvr.news_queries(dict(info, sym=sym))])

if sym == "CYCN":
    assets = {a.lower() for a in info.get("assets") or []}
    problems = []
    if not {"praliciguat", "zagociguat", "cy3018"} <= assets:
        problems.append(f"expected praliciguat, zagociguat, CY3018 in assets, got {sorted(assets)}")
    if assets & {"trontinemab", "donanemab", "lecanemab", "gantenerumab"}:
        problems.append("Korsana's own Alzheimer's drugs should not be CVR assets")
    if not any(x.lower() == "akebia" for x in info.get("companies") or []):
        problems.append("expected Akebia among companies")
    if not any(x.lower().startswith("tisento") for x in info.get("companies") or []):
        problems.append("expected Tisento among companies")
    if (info.get("obligor") or {}).get("ticker") != "KRSA":
        problems.append("expected the obligor to be KRSA (Korsana, formerly Cyclerion)")
    if problems:
        print("\nPROBLEMS:\n- " + "\n- ".join(problems))
        sys.exit(1)
    print("\nCYCN looks right.")
