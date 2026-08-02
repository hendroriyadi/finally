---
schema_version: 1
open_count: 1
waived_count: 0
fixed_count: 0
total_count: 1
last_updated: 2026-08-02T16:34:01.685Z
---

# Broken Windows Ledger

> Cross-phase defect register. `/gsd-ship` blocks while `open_count > 0`.
> Waive with `gsd-tools windows waive <id> "<reason>"` (reason required).
> Mark fixed with `gsd-tools windows fixed <id>`.

| id | phase | kind | file | line | description | status | reason | recorded_at | resolved_at |
|----|-------|------|------|------|-------------|--------|--------|-------------|-------------|
| 1 | 01 | unrun-verify | frontend/components/WatchlistRow.tsx |  | Human-check not performed: live browser verification of price flash timing/color, sparkline progressive drawing, and connection-dot resilience (stop/restart backend) — no reliable browser automation available this session | open |  | 2026-08-02T16:34:01.685Z |  |

````json
[
  {
    "id": 1,
    "kind": "unrun-verify",
    "phase": "01",
    "file": "frontend/components/WatchlistRow.tsx",
    "line": null,
    "description": "Human-check not performed: live browser verification of price flash timing/color, sparkline progressive drawing, and connection-dot resilience (stop/restart backend) — no reliable browser automation available this session",
    "status": "open",
    "reason": "",
    "recorded_at": "2026-08-02T16:34:01.685Z",
    "resolved_at": null
  }
]
````
