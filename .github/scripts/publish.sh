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

git config user.name "github-actions[bot]"
git config user.email "41898282+github-actions[bot]@users.noreply.github.com"
if [ -n "${GITHUB_ACTIONS:-}" ]; then
  # the Claude action leaves git configured with its own token, revoked when it ends: push with the workflow token
  git config --local --unset-all http.https://github.com/.extraheader || true
  git remote set-url origin "https://x-access-token:${GH_TOKEN}@github.com/${GITHUB_REPOSITORY}.git"
fi
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

git switch -q -C "$branch"
git commit -q -m "$title"
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

if [ "$state" = ready ] && [ "${AUTO_MERGE:-true}" != false ]; then
  gh pr merge "$number" --squash --delete-branch
  echo "merged"
elif [ "$state" = hold ]; then
  gh pr edit "$number" --add-label needs:maintainer > /dev/null
fi
