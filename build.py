"""Build step for the pairing/data repo (Repo A).

Runs on a slow cron (once/day) in GitHub Actions. Produces two artifacts:

  * data.json   — the machine contract consumed by the GCP watcher.
                  {generated, slots:[{slot_id, city, start, end, groups:{...}}]}
  * index.html  — the human-facing GitHub Pages view, rendered by injecting
                  the same slot data into template.html.

Design: data.json is the single source of truth. index.html is a pure view
of it, so the page and the watcher never disagree about what the slots are.

Usage:
    python build.py                 # writes data.json + index.html here
    python build.py --data-only     # only data.json (skip the page render)
"""
import argparse
import datetime
import json
import sys

from meetings import get_all_meetings
from pairing import build_slots

TEMPLATE_PATH = "template.html"
DATA_PATH = "data.json"
INDEX_PATH = "index.html"

# Markers in template.html between which the JSON payload is injected.
INJECT_START = "/*INJECT:SLOTS_DATA*/"
INJECT_END = "/*END:SLOTS_DATA*/"


def build_payload(only_future=True):
    """Fetch, pair, and assemble the data.json payload dict."""
    all_meetings = get_all_meetings(join_ftp=True)
    slots = build_slots(all_meetings, only_future=only_future)
    return {
        "generated": datetime.datetime.now(datetime.timezone.utc)
                            .strftime("%Y-%m-%dT%H:%M:%SZ"),
        "watch_scope": sorted({m.group_key
                               for mts in all_meetings.values()
                               for m in mts}),
        "slot_count": len(slots),
        "slots": [s.to_dict() for s in slots],
    }


def write_data(payload, path=DATA_PATH):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    print(f"Wrote {path}: {payload['slot_count']} slots", file=sys.stderr)


def render_index(payload, template_path=TEMPLATE_PATH, out_path=INDEX_PATH):
    """Inject payload JSON into template.html between the markers."""
    try:
        with open(template_path, "r", encoding="utf-8") as f:
            template = f.read()
    except FileNotFoundError:
        print(f"WARN: {template_path} not found; skipping index render.",
              file=sys.stderr)
        return False

    data_json = json.dumps(payload, ensure_ascii=False, indent=2)
    start = template.find(INJECT_START)
    end = template.find(INJECT_END)
    if start == -1 or end == -1 or end < start:
        print("ERROR: injection markers not found in template.html",
              file=sys.stderr)
        return False
    new_html = (template[: start + len(INJECT_START)]
                + " " + data_json + " "
                + template[end:])
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(new_html)
    print(f"Wrote {out_path}", file=sys.stderr)
    return True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-only", action="store_true",
                    help="write data.json only, skip index.html")
    ap.add_argument("--all", action="store_true",
                    help="include past meetings too (default: future only)")
    args = ap.parse_args()

    payload = build_payload(only_future=not args.all)
    write_data(payload)
    if not args.data_only:
        render_index(payload)


if __name__ == "__main__":
    main()
