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

## Install and update the signed Chrome extension

On Linux, download the signed `.crx` from the
[latest release](https://github.com/MakeEpoch/bitwarden-clients/releases/latest) and install it
from `chrome://extensions`. If browser policy requires a managed installation, use
[`ExtensionInstallForcelist`](https://chromeenterprise.google/policies/#ExtensionInstallForcelist)
with this value:

```text
aieoaondkkbpmemogejhhcgipjgllide;https://github.com/MakeEpoch/bitwarden-clients/releases/latest/download/updates.xml
```

Chrome reads `updates.xml` periodically and installs a newer CRX after verifying its signature.
Windows and macOS Chrome require an enterprise-managed configuration for this self-hosted
installation. Chrome Web Store distribution follows its own update channel.

If you currently load the ZIP as an unpacked extension, install the signed CRX once and sign
in again. The signed extension has its own stable identity and Chrome storage. Verify vault
sync before removing the previous copy. The ZIP can still be used for development.

To publish an update, run **Fork Browser** on `main` with `current_main_only` enabled, then run
`bash scripts/publish-fork-browser.sh VERSION RUN_ID`. The publisher uses the package from that
run and the local signing key at `~/.local/share/makeepoch-vault/chrome-signing.pem`.
For the same upstream version, increment the fourth component. Each signed release contains a
CRX, a matching ZIP, and `updates.xml`. Keep a secure backup of the original private key to
preserve the extension ID.
