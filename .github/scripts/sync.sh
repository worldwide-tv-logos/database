# Sourced by publish.sh, merge.sh and bulk.yml.
#
# git_setup: commits by github-actions[bot], pushed with the workflow token (GH_TOKEN).
# sync: the data change of the current branch (every commit since main) put on top of the current main, without a
# rebase: the branch is reset to main, then the index rows are merged row by row (`logos merge-data`: a row this
# change did not touch keeps main's version) and this change's logo files are applied on top (`--files`). Two versions
# of an image can therefore never stop it, and a line-by-line merge can never bring back an older row.
# Returns 0 when done, 1 when the result is not valid (a maintainer is needed), 2 when nothing is left (main already
# holds this change).

git_setup() {
  git config user.name "github-actions[bot]"
  git config user.email "41898282+github-actions[bot]@users.noreply.github.com"
  if [ -n "${GITHUB_ACTIONS:-}" ]; then
    # the Claude action leaves git configured with its own token, revoked when it ends: push with the workflow token
    git config --local --unset-all http.https://github.com/.extraheader || true
    git remote set-url origin "https://x-access-token:${GH_TOKEN}@github.com/${GITHUB_REPOSITORY}.git"
  fi
}

sync() {
  git fetch -q origin main
  local base ours msg
  base=$(git merge-base HEAD origin/main); ours=$(git rev-parse HEAD)
  if [ "$base" = "$ours" ]; then echo "nothing left once on top of main"; return 2; fi
  msg=$(git log -1 --format=%B "$(git rev-list --reverse "$base..$ours" | head -n 1)")
  git reset -q --hard origin/main
  uv run logos merge-data "$base" "$ours" --files
  git add -A data logos sources missing
  if git diff --cached --quiet; then echo "nothing left once on top of main"; return 2; fi
  git commit -q -m "$msg"
  uv run logos validate > /dev/null || { echo "data no longer valid once on top of main"; return 1; }
  uv run logos regress-check origin/main || { echo "an older version of a logo would come back"; return 1; }
}
