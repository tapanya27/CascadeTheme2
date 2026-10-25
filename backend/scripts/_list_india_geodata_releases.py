"""One-off helper: list relevant India Geodata release assets."""
from __future__ import annotations

import json
from pathlib import Path

p = Path(
    r"C:\Users\tanay\.cursor\projects\c-Users-tanay-CascadeTheme2"
    r"\agent-tools\7eba57c2-5e75-4517-99bc-9f48d24cfd58.txt"
)
releases = json.loads(p.read_text(encoding="utf-8"))
keywords = [
    "flood",
    "river",
    "ward",
    "slum",
    "road",
    "health",
    "worldpop",
    "population",
    "hydro",
    "imd",
    "dem",
    "atlas",
    "watershed",
    "stream",
    "soi",
    "nic",
]
for r in releases:
    tag = r.get("tag_name", "")
    name = r.get("name", "")
    assets = r.get("assets") or []
    blob = " ".join([tag, name] + [a["name"] for a in assets]).lower()
    if not any(k in blob for k in keywords):
        continue
    print("===", tag, "|", name)
    for a in assets:
        n = a["name"]
        sz = a["size"] / 1e6
        keep = sz < 90 or any(
            x in n.lower()
            for x in [
                "flood",
                "health",
                "worldpop",
                "atlas",
                "mumbai",
                "chennai",
                "nagpur",
                "guwahati",
                "ward",
                "slum",
                "river",
                "stream",
            ]
        )
        if keep:
            print(f"  {n:60s} {sz:7.1f} MB")
            print(f"    {a['browser_download_url']}")
