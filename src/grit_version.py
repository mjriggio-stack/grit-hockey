"""grit_version.py - Single source of truth for the GRIT version label.

Imported by every build script (scrape, build, dashboards, validation).
To bump version, edit the constant below and re-run the affected scripts.

Filename naming (raw_close_shots, grit_per_60_v3_*, grit_scores SQL table)
is INTENTIONALLY decoupled from the display version. Filenames stay v3-named
through the v3.x series for backward compatibility; display labels follow
GRIT_VERSION below.
"""

GRIT_VERSION = "v3.1"
