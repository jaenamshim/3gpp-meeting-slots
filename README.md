# 3GPP Meeting Slot Builder

Builds a daily view of upcoming 3GPP meetings, grouped into **slots**
(same city + overlapping dates), so you can see which working groups meet
together and watch every group's invitation folder — not just one.

This is **Repo A** (the slow, once-a-day data builder). A separate GCP
watcher (Repo B) consumes `data.json` and sends alerts when a slot's
Invitation folder gets new files.

## What it produces

- **`data.json`** — machine contract: paired slots with each group's FTP
  `invitation_dir` URL. Consumed by the watcher.
- **`index.html`** — human-facing GitHub Pages view (slot cards).

Both are regenerated daily by GitHub Actions and committed automatically.

## Source layout

| File | Role |
|------|------|
| `groups.py`   | 15 working groups → dynareport code + FTP paths |
| `meetings.py` | parse dynareport + join FTP folders → `Meeting` list |
| `pairing.py`  | cross-group slot pairing (city + date overlap) |
| `build.py`    | orchestrate → `data.json` + `index.html` |
| `template.html` | Pages template (JSON injected between markers) |
| `.github/workflows/build.yml` | daily cron + commit |

## Run locally

```bash
pip install -r requirements.txt
python build.py            # writes data.json + index.html
python build.py --data-only
python groups.py           # print the group registry
python meetings.py         # print upcoming meetings per group
python pairing.py          # print paired slots
```

## Watch scope

RAN1-5, SA1-6, CT1/3/4/6. (CT2, CT5 dissolved.) Online and city-less
meetings are excluded from pairing (no physical city to pair on).

## Data sources (public, no login)

- Meeting metadata: `https://www.3gpp.org/dynareport?code=Meetings-<code>.htm`
- FTP archive: `https://www.3gpp.org/ftp/`
