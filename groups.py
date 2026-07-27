"""3GPP working-group registry.

Single source of truth mapping each watched working group to:
  - its dynareport meeting-list code (for city/date metadata), and
  - its FTP working-group folder (under which per-meeting folders live).

All 15 dynareport endpoints verified reachable on 2026-07-24.
FTP folder names taken from the 3gpp-ftp-navigation skill tables.

Design notes
------------
* dynareport code is the short group token used in
  ``https://www.3gpp.org/dynareport?code=Meetings-<CODE>.htm``.
* ftp_wg_path is the folder under ``https://www.3gpp.org/ftp/<tsg>/`` that
  contains the per-meeting folders (e.g. ``TSGR1_127``). Casing: the archive
  resolves both ``tsg_ran`` and ``TSG_RAN``; we use lowercase ``tsg_*`` which
  is confirmed working.
* meeting_prefix is the folder-name prefix for this group's per-meeting
  folders, used to match meeting folders when listing the WG directory
  (RAN: ``TSGR1_``; SA2: ``TSGS2_``; CT1: ``TSGC1_``).

CT2 and CT5 are dissolved and intentionally absent.

CT meeting-folder prefixes are irregular (verified 2026-07-24 by listing
the actual WG folders):
  * CT3 folder is ``WG3_interworking_ex-CN3`` (NOT ``WG3_iopdi_ex-CN3`` as
    some references list); meetings use the regular ``TSGC3_`` prefix.
  * CT4 meetings use a bare ``CT4_`` prefix (e.g. ``CT4_136_Prague-2026-08``),
    not ``TSGC4_``.
  * CT6 meetings use ``CT6-`` with a HYPHEN (e.g. ``CT6-100_Dalian``),
    not an underscore and not ``TSGC6_``.
Everything else (RAN1-4, SA1-6, CT1) uses the regular ``TSG<code>_`` prefix.

RAN5 uses a DOUBLE underscore: ``TSGR5__112_Maastricht`` (verified
2026-07-24). Its meeting numbers also match dynareport directly once the
prefix is right.
"""

FTP_ROOT = "https://www.3gpp.org/ftp"
DYNAREPORT = "https://www.3gpp.org/dynareport?code=Meetings-{code}.htm"


class Group:
    __slots__ = ("key", "code", "tsg", "ftp_wg_path", "meeting_prefix")

    def __init__(self, key, code, tsg, ftp_wg_path, meeting_prefix):
        self.key = key                    # canonical label, e.g. "RAN1"
        self.code = code                  # dynareport code, e.g. "R1"
        self.tsg = tsg                    # "tsg_ran" | "tsg_sa" | "tsg_ct"
        self.ftp_wg_path = ftp_wg_path    # WG folder, e.g. "WG1_RL1"
        self.meeting_prefix = meeting_prefix  # per-meeting folder prefix

    @property
    def dynareport_url(self):
        return DYNAREPORT.format(code=self.code)

    @property
    def wg_dir_url(self):
        """URL of the WG folder that holds per-meeting folders."""
        return f"{FTP_ROOT}/{self.tsg}/{self.ftp_wg_path}/"

    def meeting_dir_url(self, meeting_folder):
        """URL of a specific per-meeting folder."""
        return f"{FTP_ROOT}/{self.tsg}/{self.ftp_wg_path}/{meeting_folder}/"

    def invitation_dir_url(self, meeting_folder):
        """URL of the Invitation/ subfolder — the watch target."""
        return self.meeting_dir_url(meeting_folder) + "Invitation/"

    def __repr__(self):
        return f"<Group {self.key} code={self.code}>"


# ---------------------------------------------------------------------------
# The registry. Order is display order (RAN, then SA, then CT).
# ---------------------------------------------------------------------------
GROUPS = [
    # --- RAN (tsg_ran) ---
    Group("RAN1", "R1", "tsg_ran", "WG1_RL1",           "TSGR1_"),
    Group("RAN2", "R2", "tsg_ran", "WG2_RL2",           "TSGR2_"),
    Group("RAN3", "R3", "tsg_ran", "WG3_Iu",            "TSGR3_"),
    Group("RAN4", "R4", "tsg_ran", "WG4_Radio",         "TSGR4_"),
    Group("RAN5", "R5", "tsg_ran", "WG5_Test_ex-T1",    "TSGR5__"),

    # --- SA (tsg_sa) ---
    Group("SA1", "S1", "tsg_sa", "WG1_Serv",            "TSGS1_"),
    Group("SA2", "S2", "tsg_sa", "WG2_Arch",            "TSGS2_"),
    Group("SA3", "S3", "tsg_sa", "WG3_Security",        "TSGS3_"),
    Group("SA4", "S4", "tsg_sa", "WG4_CODEC",           "TSGS4_"),
    Group("SA5", "S5", "tsg_sa", "WG5_TM",              "TSGS5_"),
    Group("SA6", "S6", "tsg_sa", "WG6_MissionCritical", "TSGS6_"),

    # --- CT (tsg_ct) --- (CT2, CT5 dissolved)
    Group("CT1", "C1", "tsg_ct", "WG1_mm-cc-sm_ex-CN1",     "TSGC1_"),
    Group("CT3", "C3", "tsg_ct", "WG3_interworking_ex-CN3", "TSGC3_"),
    Group("CT4", "C4", "tsg_ct", "WG4_protocollars_ex-CN4", "CT4_"),
    Group("CT6", "C6", "tsg_ct", "WG6_Smartcard_Ex-T3",     "CT6-"),
]

# Convenience lookups.
BY_KEY = {g.key: g for g in GROUPS}
BY_CODE = {g.code: g for g in GROUPS}


if __name__ == "__main__":
    # Self-check: print the registry so URLs can be eyeballed.
    for g in GROUPS:
        print(f"{g.key:5} code={g.code:3} "
              f"dynareport={g.dynareport_url}")
        print(f"{'':5} wg_dir={g.wg_dir_url}")
