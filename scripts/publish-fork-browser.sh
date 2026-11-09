#!/usr/bin/env bash
# Publish the local Chrome package and detached signature from a successful Fork Browser run on main.
set -euo pipefail

version=${1:?Usage: publish-fork-browser.sh VERSION RUN_ID}
run_id=${2:?Usage: publish-fork-browser.sh VERSION RUN_ID}
[[ "$run_id" =~ ^[0-9]+$ ]]
[[ "$version" =~ ^[0-9]+(\.[0-9]+){0,3}$ ]]

cd "$(dirname "$0")/.."
repo=MakeEpoch/bitwarden-clients
tag="makeepoch-v$version"
key="$HOME/.local/share/makeepoch-vault/chrome-signing.pem"

run=$(gh api "repos/$repo/actions/runs/$run_id")
workflow_id=$(gh api "repos/$repo/actions/workflows/fork-browser.yml" --jq '.id')
jq -e --argjson workflow "$workflow_id" '
  .workflow_id == $workflow and .head_branch == "main" and .conclusion == "success"
  and (.event == "workflow_dispatch" or .event == "schedule")
' <<< "$run" >/dev/null

candidate=$(gh api "repos/$repo/git/ref/heads/main" --jq '.object.sha')
artifact="makeepoch-chrome-$candidate"
previous=$(gh release view --repo "$repo" --json tagName --jq '.tagName')
[[ "$previous" == makeepoch-v* ]]

umask 077
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT

gh run download "$run_id" --repo "$repo" --name "$artifact" --dir "$work/build"
mkdir "$work/release"
python3 scripts/fork-browser-local-release.py "$work/build/dist-chrome.zip" "$work/release" \
  --version "$version" --previous "${previous#makeepoch-v}" --signing-key "$key"

(
  echo '本地解压版使用签名校验，通过配套更新器从 GitHub 接收新版。'
  echo '安装包去除了调试映射，并让弹窗和后台共用两种 WASM SDK。'
  echo
  echo '[安装和更新说明](https://github.com/MakeEpoch/bitwarden-clients/blob/main/docs/makeepoch-browser.md)'
  echo
  echo "构建来自 [GitHub Actions](https://github.com/$repo/actions/runs/$run_id)。"
  echo
  echo 'SHA-256'
  echo
  cd "$work/release"
  sha256sum -- *.zip *.sig *.py | sed 's/^/    /'
) > "$work/release-notes.md"

test "$(gh api "repos/$repo/git/ref/heads/main" --jq '.object.sha')" = "$candidate"
assets=("$work/release/"*.zip "$work/release/"*.sig "$work/release/"*.py)
if existing=$(gh release view "$tag" --repo "$repo" --json isDraft,targetCommitish 2>/dev/null); then
  jq -e --arg commit "$candidate" '.isDraft and .targetCommitish == $commit' <<< "$existing" >/dev/null
  gh release upload "$tag" --repo "$repo" --clobber "${assets[@]}"
else
  gh release create "$tag" --repo "$repo" --draft --target "$candidate" \
    --title "MakeEpoch Vault $version" --notes-file "$work/release-notes.md" "${assets[@]}"
fi

release_id=$(gh release view "$tag" --repo "$repo" --json databaseId --jq '.databaseId')
draft=$(gh api "repos/$repo/releases/$release_id")
jq -e --arg commit "$candidate" \
  '.draft and .target_commitish == $commit and (.assets | length == 3)' <<< "$draft" >/dev/null
for asset in "${assets[@]}"; do
  digest=$(sha256sum "$asset" | cut -d ' ' -f 1)
  jq -e --arg name "${asset##*/}" --arg digest "sha256:$digest" \
    'any(.assets[]; .name == $name and .state == "uploaded" and .digest == $digest)' <<< "$draft" >/dev/null
done

gh release edit "$tag" --repo "$repo" --draft=false --latest
gh api "repos/$repo/git/ref/tags/$tag" \
  | jq -e --arg commit "$candidate" '.object.sha == $commit and .object.type == "commit"' >/dev/null
