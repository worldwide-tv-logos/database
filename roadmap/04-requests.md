# Step 4: requests on our registry

**Status: done** (2026-11-23)

## Goal

Anyone, including canonical-catalog, can add a channel or correct one by opening an issue. It is checked and
applied here, with no wait on iptv-org.

## How

- **Two forms**: `channels/add` (name, country, website, other names, main channel for an edition, optional
  iptv-org and Wikidata IDs) and `channels/edit` (new name, website, other names, main channel, status, IDs, with a
  reason). A link "Add it" on every country page of the website opens `channels/add` with the country filled in.
- **Automatic checks** (`issues.py`, workflow `validate_issue`): two-letter country, a name with Latin letters or
  digits, no channel of the country already of this name (name or other names), a web address, a main channel that
  exists, iptv-org and Wikidata IDs well formed and not already another channel's; an edit changes something.
- **Review by Claude** (CLAUDE.md, "Reviewing a channel request"): the channel exists and is a TV channel of this
  country, not one listed under another name (`logos channel <name>` finds channels by name); an edition is a version
  of its main channel; an edit is backed by its reason.
- **Applied** by the nightly `update` like the other requests: a new `ch_` ID, or the channel edited (`updated` set:
  the iptv-org watch no longer overwrites it). A rename is always an edit: the channel keeps its ID and logo.
- **Logo requests**: a channel unknown here is refused with a pointer to `channels/add`; an iptv-org ID not
  registered yet still waits (`waiting:channel`), registered by the nightly `channels-init`.

## Files changed

| File | Change |
|---|---|
| `.github/ISSUE_TEMPLATE/07_channels_add.yml`, `08_channels_edit.yml` (new) | the forms |
| `worldwide_tv_logos/issues.py` | parsing, checks and application of both forms |
| `worldwide_tv_logos/cli.py` | `update` rolls back the registry of a faulty request; `logos channel <name>` finds by name |
| `worldwide_tv_logos/ops.py` | unknown channel: pointer to `channels/add` |
| `.github/workflows/validate_issue.yml` | `channels:*` requests checked and reviewed |
| `site/app/pages/countries/[cc].vue`, `composables/useCatalog.ts` | "Add it" link |
| `tests/test_logos.py` | add, duplicate, edition, taken ID, malformed fields, edit, unknown channel |
| `CLAUDE.md`, `CONTRIBUTING.md`, `site/content/docs/2.contribute/1.index.md`, `.github/docs/workflows.md` | the forms |
