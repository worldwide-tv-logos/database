# Step 4: requests on our registry

**Status: to do** (needs step 2)

## Goal

Anyone, including canonical-catalog, can add a channel or correct one by opening an issue. It is checked and
applied here, with no wait on iptv-org.

## How

- **Two new forms**: `channels: add` (name, country, website, optional parent, optional known IDs) and
  `channels: edit` (rename, website, parent, closed, extra ID).
- **Checks** (`validate_issue.yml`): country followed, no channel with the same name in the country, website
  readable and naming the channel (`sites.find`), external IDs not already mapped.
- **Applied** by `update.yml` like logo requests: `channel-add` / `channel-edit`, then the logo search of the
  next harvest.
- **`waiting:iptv-org` removed**: a logo request for a channel unknown to iptv-org creates the channel instead.

## Files to change

| File | Change |
|---|---|
| `.github/ISSUE_TEMPLATE/07_channels_add.yml`, `08_channels_edit.yml` (new) | the forms |
| `worldwide_tv_logos/issues.py` | parse and check both forms |
| `.github/workflows/validate_issue.yml`, `update.yml` | apply them |
| `.github/ISSUE_TEMPLATE/04_logos_request.yml` | channel not required to exist at iptv-org |
| `tests/test_logos.py` | parsing, refusals (duplicate, unknown country, ID already mapped) |
| `CONTRIBUTING.md`, `README.md` | how to request a channel |
