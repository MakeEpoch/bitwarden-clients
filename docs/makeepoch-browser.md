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

Build locally with Node 24 and `npm ci`, then run `npm run dist:chrome -w @bitwarden/browser`.
Extract `apps/browser/dist/dist-chrome.zip` and use Chrome's **Load unpacked** to select the
directory containing `manifest.json`.
