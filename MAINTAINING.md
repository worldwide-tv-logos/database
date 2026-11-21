# Maintaining

Maintainers review requests; the bot does everything else. A maintainer never edits `data/`, `logos/` or
`sources/` by hand.

## Daily routine

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

## Pull requests

Only for bulk imports (`uv run logos import`). Merge when the `check` workflow is green and a sample of the new
logos looks right on the PR's files tab. Commit messages are in English.

## Becoming a maintainer

Contributors with several accepted requests can ask in an issue. Maintainers have the triage role (enough to add
labels and close issues).
