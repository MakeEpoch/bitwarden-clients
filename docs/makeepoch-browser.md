# MakeEpoch Vault

This fork packages the open-source Chrome Manifest V3 extension. The extension uses the
normal Bitwarden account, vault encryption, and sync flows. Verification codes are generated
on the device from saved personal vault entries. The local Health tab scans personal logins
for weak, reused, and exposed passwords. Its optional breach scan sends only SHA-1 hash prefixes
to [Have I Been Pwned](https://haveibeenpwned.com/API/v3#PwnedPasswords).

The browser can show an operating-system reminder after filling a weak or reused personal
password. It includes no account, vault item, or site details. The phishing blocker downloads a
[public Phishing.Database feed](https://github.com/Phishing-Database/Phishing.Database) and
matches visited URLs locally. Its switch is under Settings → Account security. File Send and
the attachment management button are hidden when the account lacks their existing permissions.

## Branches and builds

- `upstream/main` mirrors [bitwarden/clients main](https://github.com/bitwarden/clients/tree/main).
- `main` contains the MakeEpoch changes and incoming upstream merge commits.
- The **Fork Browser** workflow checks for updates each day at 03:27 China Standard Time.
  It can also run manually. A successful build uploads a Chrome ZIP under the workflow run's
  **Artifacts**. The branch update is atomic and runs only after tests and packaging pass.
  Merge conflicts need to be resolved on a working branch before the next run.
- If GitHub rejects a sync that includes upstream changes to workflow files, set a
  repository secret named `FORK_SYNC_TOKEN` using a token scoped to this repository with
  Contents and Workflows write access. The token is used only by the branch update job.

Build locally with Node 24 and `npm ci`, then run:

```sh
npm run build:prod:chrome -w @bitwarden/browser
python3 scripts/package-fork-browser.py apps/browser/build apps/browser/dist/dist-chrome.zip
```

The compact package excludes sourcemaps and shares identical WASM binaries between the popup
and background. It keeps both SDK variants and the language resources.

## Install the local ZIP

Get the Chrome MV3 ZIP and `makeepoch-vault-local-updater.py` from the
[latest release](https://github.com/MakeEpoch/bitwarden-clients/releases/latest).
In `chrome://extensions`, enable developer mode and load the extracted directory once.
Use a dedicated, fixed directory for the installed extension.

If you already run an unpacked copy, keep its existing directory and ID. On Linux or macOS,
register the updater with the exact directory and ID shown in Chrome:

```sh
python3 makeepoch-vault-local-updater.py install "/absolute/path/to/existing-extension" YOUR_EXTENSION_ID
```

For a copy loaded before local updates were introduced, close Chrome and apply the first update
to the existing directory:

```sh
python3 makeepoch-vault-local-updater.py update YOUR_EXTENSION_ID
```

Restart Chrome. In **Settings → About**, choose **Enable local updates** and allow the native
messaging permission. From then on Chrome checks about every two hours when the browser is idle
and extension pages are closed. The updater verifies the package signature, stages the files,
replaces the same directory, and reloads the extension. Chrome stores the vault session and
settings under the original extension ID.

To restore the previous files, close Chrome, run
`python3 makeepoch-vault-local-updater.py rollback YOUR_EXTENSION_ID`, and restart Chrome.
The updater skips the failed version until a newer release is available.

This release channel uses an unpacked ZIP. The earlier CRX release is still available for
managed installations. The local updater currently supports Google Chrome on Linux and macOS.

## Publish a local update

Run **Fork Browser** on `main` with `current_main_only` enabled, then run
`bash scripts/publish-fork-browser.sh VERSION RUN_ID`. For the same upstream version, increment
the fourth component. The release contains the compact ZIP, its detached signature, and the
standalone updater. Keep the existing signing key at
`~/.local/share/makeepoch-vault/chrome-signing.pem` backed up securely. The updater embeds the
pinned public key and only installs verified releases.
