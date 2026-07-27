"""Build a list of Meeting records for each working group.

Two data sources are joined:

  1. dynareport (``Meetings-<code>.htm``) — authoritative for meeting NUMBER,
     CITY (Town) and DATES. Verified structure (2026-07-24): each meeting is a
     ``<tr>`` whose cells are, in order:
         td[0] meeting code link  (e.g. "R1-127")
         td[1] <a name="bmR1-127--2026-11-16">3GPPRAN1#127</a>  (title + anchor)
         td[2] Town               (e.g. "Calgary"; may be "Online" or "")
         td[3] Start date         (YYYY-MM-DD, using &#8209; non-breaking hyphen)
         td[4] End date
     dynareport does NOT expose the FTP meeting-folder name.

  2. FTP working-group directory listing — authoritative for the FTP
     meeting-FOLDER name (e.g. "TSGR1_127", "CT4_136_Prague-2026-08"), which
     is what we need to build the Invitation/ URL.

The join key is a normalized meeting identity: (number:int, is_bis:bool).
This survives the notation differences between the two sources:
    dynareport "R1-126-bis"  ~  FTP folder "TSGR1_126b"   → (126, True)
    dynareport "R1-126"      ~  FTP folder "TSGR1_126"    → (126, False)

Filtering:
  * Rows whose Town is "Online" (or empty) are kept in the list but flagged
    ``online``/``city``-empty so the pairing stage can skip them (no physical
    city → cannot pair by location).
  * Noise rows that are not real WG sessions (social events, work-planning
    calls, "1st RAN2 & SA" joint-note rows) are dropped: they have no parseable
    meeting number in the code cell (e.g. "R2--3GPP Social Even",
    "S2--Work Planning Co").
"""
import re
import time
import urllib.request
import urllib.error
from bs4 import BeautifulSoup

from groups import GROUPS, BY_KEY

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")

_DATE_RE = re.compile(r'(\d{4})\D(\d{2})\D(\d{2})')
# Meeting code cell: "<CODE>-<NUM>[-bis|b]" e.g. R1-127, R1-126-bis, S2-173.
# The trailing part after the number may carry a bis marker in various forms.
_CODE_RE = re.compile(r'^[A-Z]+\d?-(\d+)\s*(-?\s*bis|b)?', re.IGNORECASE)


# 3GPP sits behind Cloudflare and occasionally returns 503/429 under load
# (e.g. when we fetch 15 group pages back-to-back). Retry with backoff so a
# transient throttle doesn't fail the whole daily build.
_RETRY_STATUS = {429, 500, 502, 503, 504}


def _fetch(url, retries=4, backoff=3.0):
    last = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=90) as r:
                return r.read().decode('utf-8', 'replace')
        except urllib.error.HTTPError as e:
            last = e
            if e.code in _RETRY_STATUS and attempt < retries - 1:
                time.sleep(backoff * (attempt + 1))
                continue
            raise
        except (urllib.error.URLError, TimeoutError) as e:
            last = e
            if attempt < retries - 1:
                time.sleep(backoff * (attempt + 1))
                continue
            raise
    if last:
        raise last


def _norm_date(s):
    m = _DATE_RE.search(s.replace('&#8209;', '-'))
    return f"{m.group(1)}-{m.group(2)}-{m.group(3)}" if m else None


class Meeting:
    __slots__ = ("group_key", "number", "is_bis", "title", "city",
                 "start", "end", "folder", "online")

    def __init__(self, group_key, number, is_bis, title, city, start, end):
        self.group_key = group_key   # "RAN1"
        self.number = number         # int, e.g. 127
        self.is_bis = is_bis         # bool
        self.title = title           # "3GPPRAN1#127"
        self.city = city             # "Calgary" | "" | "Online"
        self.start = start           # "2026-11-16"
        self.end = end               # "2026-11-20"
        self.folder = None           # FTP folder name, filled by join
        self.online = (city or "").strip().lower() == "online"

    @property
    def ident(self):
        """Join key shared between dynareport row and FTP folder."""
        return (self.number, self.is_bis)

    @property
    def pairable(self):
        """Only meetings with a real physical city and dates can be paired."""
        return bool(self.start and self.city and not self.online)

    # Titles like "3GPPSA3#102-LI-bis" denote a sub-group / special session
    # (Lawful Interception, ad-hoc, joint) that runs alongside the main WG
    # meeting but is a distinct body. We watch the MAIN WG meeting, so these
    # are treated as non-primary when a group has several meetings in one slot.
    _SUBGROUP_RE = re.compile(r'-(LI|AH|adhoc|ah)\b', re.IGNORECASE)

    @property
    def is_subgroup(self):
        return bool(self._SUBGROUP_RE.search(self.title or ""))

    @property
    def primacy(self):
        """Sort key to pick the representative meeting for a (group, slot):
        prefer a main-WG meeting (not sub-group), then the higher number."""
        return (0 if self.is_subgroup else 1, self.number)

    def invitation_dir_url(self):
        if not self.folder:
            return None
        return BY_KEY[self.group_key].invitation_dir_url(self.folder)

    def meeting_dir_url(self):
        if not self.folder:
            return None
        return BY_KEY[self.group_key].meeting_dir_url(self.folder)

    def __repr__(self):
        b = "bis" if self.is_bis else ""
        return (f"<Meeting {self.group_key}#{self.number}{b} "
                f"{self.city!r} {self.start} folder={self.folder}>")


def parse_dynareport(group):
    """Return list[Meeting] parsed from a group's dynareport page.

    Noise rows (no meeting number in the code cell) are dropped.
    """
    html = _fetch(group.dynareport_url)
    soup = BeautifulSoup(html, 'html.parser')
    meetings = []
    for tr in soup.find_all('tr'):
        tds = tr.find_all('td')
        if len(tds) < 5:
            continue
        code_txt = tds[0].get_text(strip=True)
        m = _CODE_RE.match(code_txt)
        if not m:
            # Social events, work-planning calls, joint-note rows → skip.
            continue
        number = int(m.group(1))
        is_bis = bool(m.group(2))
        title = tds[1].get_text(strip=True)
        city = tds[2].get_text(strip=True)
        start = _norm_date(tds[3].get_text())
        end = _norm_date(tds[4].get_text())
        meetings.append(Meeting(group.key, number, is_bis, title,
                                city, start, end))

    # Some groups (notably SA4/SA5) list the same meeting as several rows,
    # one per sub-working-group session. Collapse by (number, is_bis, start),
    # preferring a row that has a non-empty, non-Online city.
    dedup = {}
    for mt in meetings:
        key = (mt.number, mt.is_bis, mt.start)
        cur = dedup.get(key)
        if cur is None:
            dedup[key] = mt
            continue
        # Prefer the record with a usable physical city.
        if (not cur.pairable) and mt.pairable:
            dedup[key] = mt
    return list(dedup.values())


# FTP folder → (number, is_bis). Prefix already stripped by caller.
# Examples of the remainder: "127", "126b", "126bis", "133-bis",
# "136_Prague-2026-08", "125_LaCiotat_2026-02", "AH" (→ no number → None).
# The bis marker appears as: "b", "bis", or "-bis" right after the number.
_FOLDER_NUM_RE = re.compile(r'^(\d+)\s*(-?\s*bis|b)?', re.IGNORECASE)


def _folder_ident(group, folder):
    rest = folder[len(group.meeting_prefix):]
    m = _FOLDER_NUM_RE.match(rest)
    if not m:
        return None
    return (int(m.group(1)), bool(m.group(2)))


def list_ftp_folders(group):
    """Return {(number, is_bis): folder_name} for a group's WG directory."""
    html = _fetch(group.wg_dir_url)
    soup = BeautifulSoup(html, 'html.parser')
    result = {}
    for a in soup.find_all('a'):
        name = (a.get_text(strip=True) or a.get('href') or '')
        name = name.strip('/').split('/')[-1]
        if not name.startswith(group.meeting_prefix):
            continue
        ident = _folder_ident(group, name)
        if ident is None:
            continue
        # If two folders map to the same ident (rare), prefer the longer name
        # (usually the one with city/date suffix, i.e. the real meeting).
        if ident not in result or len(name) > len(result[ident]):
            result[ident] = name
    return result


def get_meetings(group, join_ftp=True):
    """Full pipeline for one group: parse dynareport, then attach FTP folder
    names by joining on (number, is_bis)."""
    meetings = parse_dynareport(group)
    if join_ftp:
        folders = list_ftp_folders(group)
        for mt in meetings:
            mt.folder = folders.get(mt.ident)
    return meetings


def get_all_meetings(groups=GROUPS, join_ftp=True):
    """Return {group_key: list[Meeting]} for every watched group."""
    return {g.key: get_meetings(g, join_ftp=join_ftp) for g in groups}


if __name__ == "__main__":
    import datetime
    today = datetime.date.today().isoformat()
    for g in GROUPS:
        mts = get_meetings(g)
        future = [m for m in mts if m.start and m.start >= today]
        future.sort(key=lambda m: m.start)
        print(f"\n=== {g.key}: {len(mts)} total, {len(future)} upcoming ===")
        for m in future[:4]:
            tag = "  [ONLINE]" if m.online else ("" if m.pairable else "  [no-city]")
            print(f"  #{m.number}{'bis' if m.is_bis else '':3} "
                  f"{m.start}~{m.end} {m.city:20} folder={m.folder}{tag}")
