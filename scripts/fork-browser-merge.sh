#!/usr/bin/env bash
# Return the deterministic merge commit that will be built and promoted.
set -euo pipefail

base=$1
upstream=$2

if git merge-base --is-ancestor "$upstream" "$base"; then
  git rev-parse "$base"
  exit
fi

if ! tree=$(git merge-tree --write-tree "$base" "$upstream"); then
  printf '%s\n' "$tree" >&2
  echo "Upstream conflicts with the fork. Resolve the merge on a branch before retrying." >&2
  exit 1
fi

# Both jobs must generate the same commit without passing executable data
# from the build job to the job with permission to update the branches.
export GIT_AUTHOR_NAME='MakeEpoch Upstream Sync'
export GIT_COMMITTER_NAME="$GIT_AUTHOR_NAME"
export GIT_AUTHOR_EMAIL='41898282+github-actions[bot]@users.noreply.github.com'
export GIT_COMMITTER_EMAIL="$GIT_AUTHOR_EMAIL"
GIT_AUTHOR_DATE=$(git show -s --format=%cI "$upstream")
export GIT_AUTHOR_DATE
export GIT_COMMITTER_DATE="$GIT_AUTHOR_DATE"

git -c commit.gpgsign=false commit-tree "$tree" -p "$base" -p "$upstream" \
  -m "Merge Bitwarden upstream main"
