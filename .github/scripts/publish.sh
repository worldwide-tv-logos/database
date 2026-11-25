#!/usr/bin/env bash
# Publish the data changes of a workflow as a pull request, and merge it when allowed.
#
#   publish.sh <branch> <title> <body file>
#
# Only data/, logos/, sources/ and missing/ are committed (never code, workflows or instructions). The pull request
# body is the body file followed by the reviewer's report (temp/verdict.json, written by `logos verdict`). The pull
# request is merged only when the reviewer said `ready` and `logos validate` passes, unless the repository variable
# AUTO_MERGE is `false`; otherwise it waits for a maintainer (label needs:maintainer when the reviewer said `hold`).
set -euo pipefail
branch=$1 title=$2 body=$3

source "$(dirname "$0")/sync.sh"
git_setup
uv run logos validate
git add data logos sources missing
if git diff --cached --quiet; then echo "nothing to publish"; exit 0; fi

state=hold
if [ -s temp/verdict.json ]; then
  state=$(python3 -c 'import json; print(json.load(open("temp/verdict.json"))["state"])')
  { cat "$body"; echo; echo "---"; echo; python3 -c 'import json; print(json.load(open("temp/verdict.json"))["text"])'; } > temp/pr-body.md
else
  { cat "$body"; echo; echo "---"; echo; echo "No review recorded: a maintainer must review this pull request."; } > temp/pr-body.md
fi
# GitHub refuses a body over 65,536 characters (a country with hundreds of logos found): cut it, keep the review
python3 - <<'EOF'
from pathlib import Path
p = Path('temp/pr-body.md'); text = p.read_text(encoding='utf-8'); limit = 60000
if len(text) > limit:
    head, sep, review = text.rpartition('\n---\n')
    cut = '\n\n*(list cut: too long for a pull request body, see the files changed)*\n'
    keep = max(0, limit - len(cut) - len(sep) - len(review))
    p.write_text((head[:keep] + cut + sep + review)[:limit], encoding='utf-8')
EOF

# On top of the current main (sync.sh: no rebase, rows merged row by row, our logo files applied on top).
git switch -q -C "$branch"
git commit -q -m "$title"
rc=0; sync || rc=$?
if [ $rc = 2 ]; then echo "nothing to publish once on top of main"; exit 0; fi
[ $rc = 0 ] || state=hold
git push -q -f origin "$branch"
number=$(gh pr list --head "$branch" --state open --json number --jq '.[0].number')
if [ -z "$number" ]; then
  gh pr create --head "$branch" --base main --title "$title" --body-file temp/pr-body.md > /dev/null
  number=$(gh pr view "$branch" --json number --jq .number)
else
  gh pr edit "$number" --body-file temp/pr-body.md > /dev/null
fi
echo "pull request #$number, review: $state"
[ -n "${GITHUB_OUTPUT:-}" ] && echo "pr=$number" >> "$GITHUB_OUTPUT"

if [ "$state" = ready ]; then
  # review:ready: merged now, or by the retry workflow when main moved meanwhile
  gh label create review:ready --color 0e8a16 --description "reviewed and ready: merged automatically" > /dev/null 2>&1 || true
  gh pr edit "$number" --remove-label needs:maintainer --add-label review:ready > /dev/null 2>&1 || true
  if [ "${AUTO_MERGE:-true}" != false ]; then bash "$(dirname "$0")/merge.sh" "$number" "$branch" || true; fi
else
  gh pr edit "$number" --remove-label review:ready --add-label needs:maintainer > /dev/null 2>&1 || true
fi
