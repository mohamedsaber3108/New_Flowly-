"""Read-only access to the static Flowly catalog exported from the frontend (lib/catalog.ts).

The catalog stays source-controlled (no CMS in the MVP). data/catalog.json holds the
45 services (EN/AR name + description), the 14 industry slugs and the 3 insight slugs.
"""

import json
from functools import lru_cache
from pathlib import Path

DATA_FILE = Path(__file__).resolve().parent / "data" / "catalog.json"


@lru_cache(maxsize=1)
def load():
    with DATA_FILE.open(encoding="utf-8") as handle:
        return json.load(handle)


def services():
    return load()["services"]


def service_map():
    return {s["id"]: s for s in services()}


def site_paths():
    data = load()
    base = ["/", "/services", "/industries", "/government", "/about", "/approach", "/engagement", "/insights"]
    return (
        base
        + [f"/services/{s['id']}" for s in data["services"]]
        + [f"/industries/{slug}" for slug in data["industries"]]
        + [f"/insights/{slug}" for slug in data["insights"]]
    )
