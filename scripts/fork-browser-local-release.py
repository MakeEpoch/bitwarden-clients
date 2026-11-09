#!/usr/bin/env python3
"""Stamp and sign the unpacked Chrome ZIP, and prepare the standalone native updater."""

import argparse
import json
from pathlib import Path
import subprocess
from zipfile import ZIP_DEFLATED, ZipFile

from importlib import import_module

release = import_module("fork-browser-release")
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("package", type=Path)
parser.add_argument("output", type=Path)
parser.add_argument("--version", required=True)
parser.add_argument("--previous", required=True)
parser.add_argument("--signing-key", type=Path, required=True)
args = parser.parse_args()

if release.public_der(args.signing_key) != release.public_der(release.PUBLIC_KEY, public=True):
    raise ValueError("The signing key does not match the pinned MakeEpoch identity")
version = release.version_tuple(args.version)
if version <= release.version_tuple(args.previous):
    raise ValueError("The release version must be higher than the latest release")

archive = args.output / f"makeepoch-vault-{args.version}-chrome-mv3.zip"
with ZipFile(args.package) as source:
    manifest = json.loads(source.read("manifest.json"))
    base = release.version_tuple(manifest["version"])
    if (
        manifest.get("name") != "MakeEpoch Vault" or manifest.get("manifest_version") != 3
        or version[:3] != base[:3] or version < base
        or "key" in manifest or "update_url" in manifest
        or json.loads(source.read("makeepoch-local.json")) != {"channel": "local"}
        or source.testzip()
    ):
        raise ValueError("Expected a verified compact MakeEpoch local build")
    manifest["version"] = args.version
    with ZipFile(archive, "w", compression=ZIP_DEFLATED, compresslevel=6) as target:
        for entry in source.infolist():
            data = json.dumps(manifest, indent=2).encode() if entry.filename == "manifest.json" else source.read(entry)
            target.writestr(entry.filename, data)

subprocess.run(
    ["openssl", "dgst", "-sha256", "-sign", str(args.signing_key), "-out", f"{archive}.sig", str(archive)],
    check=True,
)
updater = Path(__file__).with_name("makeepoch-vault-local-updater.py").read_text()
placeholder = 'PUBLIC_KEY = b""'
assert updater.count(placeholder) == 1
(args.output / "makeepoch-vault-local-updater.py").write_text(
    updater.replace(placeholder, f"PUBLIC_KEY = {release.PUBLIC_KEY.read_bytes()!r}")
)
