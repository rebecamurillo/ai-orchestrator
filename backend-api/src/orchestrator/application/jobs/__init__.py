"""The two scheduled jobs SPEC CAP-11 registers through `engine.schedule` (AD-6): pure
application functions over ports, wired to a cron and a DBOS scheduled workflow only in
`infrastructure/` (`infrastructure/jobs.py`) — this package never imports `dbos`.
"""

from __future__ import annotations
