"""Pairing engine: group meetings across ALL working groups into "slots".

A *slot* is a set of meetings that happen in the same physical city during
overlapping dates. The whole point of this project: if any group in a slot
gets its invitation posted, delegates start booking, so we want to watch
every group in the slot — not just RAN1.

Pairing rule (confirmed with the user):
    two meetings belong to the same slot  ⇔
        their date ranges OVERLAP  AND  their normalized cities MATCH.

Only ``meeting.pairable`` meetings participate (real physical city + dates;
Online / city-less / noise rows are excluded upstream in meetings.py).

City normalization
------------------
dynareport city strings are mostly consistent *within* a given slot (all
groups meeting together copy the same Town string), but vary in casing and
decoration across the archive. We normalize conservatively:
  * lowercase, collapse whitespace
  * strip apostrophes and punctuation
  * drop common decorative suffixes ("metropolitan area", "area")
  * apply an explicit alias table for known country/city equivalences
This is deliberately light — we do NOT try to canonicalize every city on
Earth, only to absorb the notation noise actually seen in 3GPP data.
"""
import re
import datetime

from meetings import get_all_meetings


# Decorative tails that show up in Town strings and carry no identity.
_DECORATIVE = [
    "metropolitan area",
    "greater area",
    " area",
]

# Explicit equivalences. Left side is already lowercased/space-collapsed.
# Kept intentionally small; extend only when a real mismatch is observed.
_CITY_ALIASES = {
    # country-name Towns that 3GPP sometimes uses instead of the host city.
    # These only matter if two groups in the *same* week use different
    # granularity (country vs city). Left as identity unless proven needed.
}


def normalize_city(city):
    """Return a normalized city key, or '' if not usable."""
    if not city:
        return ""
    s = city.strip().lower()
    s = s.replace("'", "").replace("\u2019", "")   # apostrophes
    s = re.sub(r"[.,]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    for tail in _DECORATIVE:
        if s.endswith(tail):
            s = s[: -len(tail)].strip()
    s = _CITY_ALIASES.get(s, s)
    return s


def _to_date(s):
    return datetime.date.fromisoformat(s) if s else None


def _overlaps(a_start, a_end, b_start, b_end):
    """Inclusive date-range overlap."""
    return not (a_end < b_start or b_end < a_start)


class Slot:
    def __init__(self, city_norm, city_display, start, end):
        self.city_norm = city_norm
        self.city_display = city_display   # human-readable, from first member
        self.start = start                 # earliest start among members
        self.end = end                     # latest end among members
        self.members = []                  # list[Meeting]

    def add(self, mt):
        self.members.append(mt)
        ms, me = _to_date(mt.start), _to_date(mt.end)
        if ms < self.start:
            self.start = ms
        if me > self.end:
            self.end = me

    def representatives(self):
        """One meeting per group — the primary (main-WG, highest number)."""
        best = {}
        for m in self.members:
            cur = best.get(m.group_key)
            if cur is None or m.primacy > cur.primacy:
                best[m.group_key] = m
        return best

    @property
    def slot_id(self):
        return f"{self.start.strftime('%Y-%m')}_{self.city_display.replace(' ', '')}"

    @property
    def groups(self):
        """Sorted list of group keys present in this slot."""
        return sorted(self.representatives().keys(), key=_group_sort_key)

    def to_dict(self):
        """Serialize to the data.json slot schema. One entry per GROUP,
        using the primary (representative) meeting for each group."""
        reps = self.representatives()
        groups = {}
        for gk in sorted(reps.keys(), key=_group_sort_key):
            m = reps[gk]
            groups[gk] = {
                "meeting_number": m.number,
                "is_bis": m.is_bis,
                "meeting_folder": m.folder,
                "meeting_dir": m.meeting_dir_url(),
                "invitation_dir": m.invitation_dir_url(),
            }
        return {
            "slot_id": self.slot_id,
            "city": self.city_display,
            "city_norm": self.city_norm,
            "start": self.start.isoformat(),
            "end": self.end.isoformat(),
            "groups": groups,
        }

    def __repr__(self):
        return (f"<Slot {self.city_display} {self.start}~{self.end} "
                f"groups={self.groups}>")


# Group ordering for stable display: RAN1..5, SA1..6, CT1/3/4/6.
_GROUP_ORDER = {
    "RAN1": 1, "RAN2": 2, "RAN3": 3, "RAN4": 4, "RAN5": 5,
    "SA1": 11, "SA2": 12, "SA3": 13, "SA4": 14, "SA5": 15, "SA6": 16,
    "CT1": 21, "CT3": 23, "CT4": 24, "CT6": 26,
}


def _group_sort_key(gk):
    return _GROUP_ORDER.get(gk, 99)


def build_slots(all_meetings, only_future=True, today=None):
    """Group meetings from all groups into slots.

    Parameters
    ----------
    all_meetings : {group_key: [Meeting, ...]}
    only_future  : keep only meetings whose end date is today or later.
    """
    if today is None:
        today = datetime.date.today()

    # Flatten to a single pairable list.
    flat = []
    for gk, mts in all_meetings.items():
        for m in mts:
            if not m.pairable:
                continue
            if only_future and _to_date(m.end) < today:
                continue
            flat.append(m)

    # Greedy grouping: for each meeting, find an existing slot with matching
    # normalized city AND date overlap; else start a new slot. Because same-
    # slot meetings share both city and week, this is stable and O(n·slots).
    slots = []
    # Sort by start date so slot date-bounds grow predictably.
    for m in sorted(flat, key=lambda x: x.start):
        cn = normalize_city(m.city)
        ms, me = _to_date(m.start), _to_date(m.end)
        placed = False
        for s in slots:
            if s.city_norm != cn:
                continue
            if _overlaps(ms, me, s.start, s.end):
                s.add(m)
                placed = True
                break
        if not placed:
            s = Slot(cn, m.city.strip(), ms, me)
            s.add(m)
            slots.append(s)

    slots.sort(key=lambda s: (s.start, s.city_display))
    return slots


if __name__ == "__main__":
    print("Fetching all groups (this hits the network for 15 groups)...")
    all_m = get_all_meetings()
    slots = build_slots(all_m, only_future=True)
    print(f"\n{len(slots)} upcoming slots:\n")
    for s in slots:
        reps = s.representatives()
        gl = ", ".join(
            f"{gk}#{reps[gk].number}{'bis' if reps[gk].is_bis else ''}"
            for gk in sorted(reps.keys(), key=_group_sort_key))
        print(f"  {s.start}~{s.end}  {s.city_display:22}  [{len(s.groups)} grp]  {gl}")
