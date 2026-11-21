# Maintaining

Maintainers review requests; the bot does everything else. A maintainer never edits `data/`, `logos/` or
`sources/` by hand.

## Daily routine

Claude decides every request and every logo of the pull requests it prepares (see CLAUDE.md): it approves the
right requests and closes the others with the reason, rejects the wrong or unverifiable harvested logos, and the
pull requests are merged automatically. Your part is only what is labelled
[`needs:maintainer`](../../issues?q=is%3Aopen+label%3Aneeds%3Amaintainer) (something broken), and checking
Claude's decisions from time to time (monthly report). Write `@claude` in an issue or pull request to ask it
something.

1. Open the [requests that passed the checks](../../issues?q=is%3Aopen+label%3Acheck%3Apassed+-label%3Aapproved).
2. For each one, review it (below), then add the `approved` label, or comment and close it.
3. Done: the nightly `update` workflow (03:00 UTC) applies each approved request alone, commits it, closes the
   issue with a summary, and the `deploy` workflow publishes the site.

A request labelled `check:failed` waits for its author: the bot has already explained what to fix, and checks it
again when the issue is edited. Close it after 30 days without an answer.

## Reviewing a request

| Request | Check |
|---|---|
| logos/add, logos/edit | the image is the logo **currently on air** for this exact channel or edition (compare with the channel's website or a recent screenshot); it is not a festival, event or temporary logo; the source looks official or faithful |
| logos/remove | the reason is real (wrong channel, outdated branding, poor quality); a closed channel can keep its logo |
| logos/request | nothing to approve: leave it open until someone answers with logos/add, then close it |
| aliases/add | the guide really uses this ID for this channel (open the guide's channel list) |
| aliases/remove | the alias is wrong or the guide dropped it |

The bot has already checked the IDs, the image (format, size, transparency) and duplicates. If a request is edited
after its approval, the bot withdraws the approval: review it again.

A channel that is not in iptv-org yet can be approved: it waits with `waiting:iptv-org` and is applied the night
iptv-org adds it.

## Changes on the iptv-org side

Every Monday the `changes` workflow updates the issue labelled
[`iptv-org:changes`](../../issues?q=is%3Aopen+label%3Aiptv-org%3Achanges): logos whose channel was removed, closed
or replaced in iptv-org. Fix them with ordinary requests (logos/add for the new ID, logos/remove for the old one);
the issue closes by itself when the list is empty.

## Weekly harvest pull requests

Every Sunday the `harvest` workflow looks for the logos of each country of `data/countries.csv` (iptv-org and
Wikidata): missing logos, and newer or better versions of current ones (original changed at its source, SVG found,
much larger, logo replaced in iptv-org). It opens one pull request per country, `Weekly harvest: <country>`, unless
the previous one is still open.

1. Open the *Files changed* tab: every new logo is shown, and an update is shown before and after.
2. Check each one like a logos/add request: the logo currently on air for this exact channel.
3. Refuse a logo by commenting `/reject <channel id> <reason>` (e.g. `/reject Cuatro.es old branding`): the bot
   removes it from the pull request and adds it to `data/rejected.csv`, so it is never proposed again.
4. Merge. Images the bot was unsure about (the same image for several channels) are listed as doubts and are not
   in the pull request.

A country is followed by adding its line to `data/countries.csv` (code, name). On Wednesdays the `hunt` pull
requests bring the logos of channels that had none, found the same way and reviewed by Claude.

## Letting Claude merge

Pull requests prepared by Claude (harvest, hunt, requests, iptv-org changes) contain data only. They are merged
automatically when Claude says they are ready and `logos validate` passes; Claude says `hold` only when something
is broken, and they then wait for a maintainer (label `needs:maintainer`). To review everything by hand for a while, create the repository variable
`AUTO_MERGE` with the value `false` (Settings > Secrets and variables > Actions > Variables); delete it to let Claude
merge again. The monthly `report` issue sums up what Claude did, and any merged change can be reverted.

## Other pull requests

Only for bulk imports (`uv run logos import`). Merge when the `check` workflow is green and a sample of the new
logos looks right on the PR's files tab. Commit messages are in English.

## Becoming a maintainer

Contributors with several accepted requests can ask in an issue. Maintainers have the triage role (enough to add
labels and close issues), or the write role to also merge harvest pull requests.
