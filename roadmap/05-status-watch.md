# Step 5: status watch

**Status: to do** (needs step 2)

## Goal

A channel is marked `closed` only when several independent signals agree, and its logos are kept. A channel that
reappears is reopened.

## How

- **Signals**, gathered weekly per channel:
  - iptv-org `closed` date (step 3);
  - Wikidata "dissolved" (P576) or "end time" (P582);
  - no programmes in any mapped guide for 14 days;
  - website dead, or redirected to another channel's site (`web.fetch`, `sites.find`).
- **Decision**: two signals or more → proposal in a weekly pull request reviewed by Claude, like site-check
  (`status set <id> closed --reason`). One signal alone → listed only.
- **Health**: proposals left unreviewed for seven days appear in the `health` issue.

## Files to change

| File | Change |
|---|---|
| `worldwide_tv_logos/status.py` (new) | signals, decision, summary |
| `worldwide_tv_logos/sources/wikidata.py` | read P576 / P582 |
| `worldwide_tv_logos/sources/iptvepg.py` | last programme date per guide channel |
| `worldwide_tv_logos/cli.py` | `logos status-check`, `logos status set` |
| `.github/workflows/status_check.yml` (new) | weekly, with Claude review and `publish.sh` |
| `tests/test_logos.py` | signals combined, reopening |
| `CLAUDE.md`, `.github/docs/workflows.md` | the watch and how to review it |
