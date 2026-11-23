# Step 3: iptv-org watch

**Status: done** (2026-11-23; first run: Sky Sports Arena renamed Sky Sports+, same channel here, its empty
duplicate absorbed)

## Goal

Every day, what changed at iptv-org is applied to our registry: new channels get a `ch_` ID, renamed channels keep
theirs, closed channels are marked. Their open issues give early notice of what is coming.

## How

- **Every night** (`update`): `logos watch-iptvorg`, then `logos channels-init`, committed with the summary.
  No previous copy is needed: the registry itself is compared with iptv-org's current `channels.json`.
  - renamed (`replaced_by`, followed along a chain): the new iptv-org ID is mapped to the **same `ch_`**, the old one
    kept as `iptv-org-former` (it still finds the channel and is never registered again); its editions follow
    (`X@Alsace` -> `Y@Alsace`); name and slug follow. If the new ID was already registered as another channel:
    absorbed when it has nothing of its own (no logo, alias, edit or Wikidata ID); otherwise it is the current
    channel, and ours becomes `merged` into it (both logos kept);
  - closed: status `closed`, logo kept; open again: `active` (a signal for step 5, which adds others);
  - name, other names, website: taken from iptv-org unless the channel was edited here (`updated` set);
  - removed without a successor: listed, never removed here.
- **Every Monday** (`changes`): the `iptv-org:changes` issue lists the logos of channels renamed in the week (a
  rename often comes with a new branding: Claude checks it with `logos find` and the website), the channels no longer
  in iptv-org, and the requests open at iptv-org (`channels:add`, `channels:edit`, `channels:remove`) for the
  followed countries, as information: never applied before iptv-org accepts them.
- Applied directly every night rather than in a pull request: the rules are mechanical and keep every logo; what
  needs judgement goes to the weekly issue.

## Files changed

| File | Change |
|---|---|
| `worldwide_tv_logos/watch.py` (new) | renames, absorption or merge, closures, names; renamed logos to check; coming requests |
| `worldwide_tv_logos/registry.py` | `iptv-org-former` and `iptv-org-feed-former` sources, found by `resolve` and `by_logo_id` |
| `worldwide_tv_logos/cli.py` | `logos watch-iptvorg`; `logos changes` with renamed logos and coming requests |
| `.github/workflows/update.yml` | `watch-iptvorg` before `channels-init`, summary in the commit message |
| `.github/workflows/changes.yml` | Claude checks renamed logos instead of moving them |
| `tests/test_logos.py` | rename with editions and absorption, merge, closures, edits left alone, coming requests |
| `MAINTAINING.md`, `.github/docs/*.md` | the watch |
