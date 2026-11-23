# Step 3: iptv-org watch

**Status: to do** (needs step 2)

## Goal

Every day, what changed at iptv-org is applied to our registry: new channels get a `ch_` ID, renamed channels keep
theirs, closed channels are marked. Their open issues give early notice of what is coming.

## How

- **Daily diff** of `channels.json` and `feeds.json` against the previous copy (kept in the Actions cache):
  - new channel in a followed country: new `ch_` + mapping (then searched by the next harvest);
  - `replaced_by` or renamed: **same `ch_`**, new name and slug, new iptv-org ID added to the mapping;
  - `closed` set: status proposal for step 5 (not applied alone);
  - removed: mapping kept, flagged for review.
- **Issues** (`gh api`, labels `channels:add`, `channels:edit`, `channels:remove`): read only, listed in the daily
  pull request as "coming soon", never applied before iptv-org merges them.
- **One pull request per day** through `publish.sh`, merged automatically when it only adds IDs or renames.

## Files to change

| File | Change |
|---|---|
| `worldwide_tv_logos/iptvorg.py` | load `feeds.json`; keep the previous copy |
| `worldwide_tv_logos/watch.py` (new) | diff, rules above, summary |
| `worldwide_tv_logos/cli.py` | `logos watch-iptvorg` |
| `.github/workflows/changes.yml` | run every day, then `publish.sh` |
| `tests/test_logos.py` | new / renamed / closed / removed cases |
| `CLAUDE.md`, `.github/docs/workflows.md` | the watch |
