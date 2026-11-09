#!/usr/bin/env python3
"""Build the signed Chrome release and its update manifest from a tested ZIP."""

import argparse
import base64
import hashlib
from io import BytesIO
import json
from pathlib import Path
import re
import struct
import subprocess
from tempfile import TemporaryDirectory
from xml.etree import ElementTree as ET
from zipfile import ZipFile

RELEASES = "https://github.com/MakeEpoch/bitwarden-clients/releases"
UPDATE_URL = f"{RELEASES}/latest/download/updates.xml"
TAG_PREFIX = "makeepoch-v"
PUBLIC_KEY = Path(__file__).resolve().parents[1] / "apps/browser/config/makeepoch-chrome-update.pub"


def version_tuple(version):
    if not re.fullmatch(r"(?:0|[1-9][0-9]{0,4})(?:\.(?:0|[1-9][0-9]{0,4})){0,3}", version):
        raise ValueError(f"Invalid Chrome version: {version}")
    parts = [int(part) for part in version.split(".")]
    if max(parts) > 65535 or not any(parts):
        raise ValueError(f"Invalid Chrome version: {version}")
    return tuple(parts + [0] * (4 - len(parts)))


def public_der(key, *, public=False):
    args = ["openssl", "pkey", "-in", str(key), "-outform", "DER"]
    args += ["-pubin"] if public else ["-pubout"]
    return subprocess.check_output(args)


def extension_id(public_key):
    digest = hashlib.sha256(public_key).hexdigest()[:32]
    return digest.translate(str.maketrans("0123456789abcdef", "abcdefghijklmnop"))


def stage_extension(package, extension, version, previous, public_key):
    with ZipFile(package) as source:
        if source.testzip():
            raise ValueError("The source archive failed its CRC check")
        manifest = json.loads(source.read("manifest.json"))
        if manifest["manifest_version"] != 3 or manifest["name"] != "MakeEpoch Vault":
            raise ValueError("Expected a MakeEpoch Vault Chrome MV3 archive")
        base_version = version_tuple(manifest["version"])
        target = version_tuple(version)
        if target[:3] != base_version[:3] or target < base_version:
            raise ValueError("The release version must match the built upstream version and may add a fork revision")
        if previous is not None and target <= version_tuple(previous):
            raise ValueError("The release version must be higher than the latest release")
        source.extractall(extension)

    manifest.update(
        version=version,
        key=base64.b64encode(public_key).decode("ascii"),
        update_url=UPDATE_URL,
    )
    (extension / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    return manifest


def signed_payload(crx, expected_manifest):
    if len(crx) < 12:
        raise ValueError("Invalid Chrome package")
    magic, version, header_size = struct.unpack("<4sII", crx[:12])
    if magic != b"Cr24" or version != 3 or header_size == 0:
        raise ValueError("Expected a signed CRX3 package")
    payload = crx[12 + header_size :]
    if not payload.startswith(b"PK\x03\x04"):
        raise ValueError("The CRX3 archive payload is missing")
    with ZipFile(BytesIO(payload)) as archive:
        manifest = json.loads(archive.read("manifest.json"))
        if manifest != expected_manifest or archive.testzip():
            raise ValueError("The signed package contents failed verification")
    return payload


def write_update_manifest(path, manifest, identifier, crx_name):
    update = ET.Element("gupdate", xmlns="http://www.google.com/update2/response", protocol="2.0")
    app = ET.SubElement(update, "app", appid=identifier)
    ET.SubElement(
        app,
        "updatecheck",
        codebase=f"{RELEASES}/download/{TAG_PREFIX}{manifest['version']}/{crx_name}",
        version=manifest["version"],
        prodversionmin=manifest["minimum_chrome_version"],
    )
    ET.ElementTree(update).write(path, encoding="utf-8", xml_declaration=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("package", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--version", required=True)
    parser.add_argument("--previous")
    parser.add_argument("--signing-key", type=Path, required=True)
    parser.add_argument("--chrome", default="google-chrome")
    args = parser.parse_args()

    public_key = public_der(PUBLIC_KEY, public=True)
    if public_der(args.signing_key) != public_key:
        raise ValueError("The signing key does not match the pinned MakeEpoch Chrome identity")

    with TemporaryDirectory(prefix="makeepoch-crx-") as work:
        work = Path(work)
        extension = work / "extension"
        manifest = stage_extension(args.package, extension, args.version, args.previous, public_key)
        subprocess.run(
            [
                args.chrome,
                "--no-sandbox",
                f"--user-data-dir={work / 'chrome-profile'}",
                f"--pack-extension={extension}",
                f"--pack-extension-key={args.signing_key.resolve()}",
            ],
            check=True,
        )
        crx = extension.with_suffix(".crx").read_bytes()
        payload = signed_payload(crx, manifest)

    args.output.mkdir(parents=True, exist_ok=True)
    stem = f"makeepoch-vault-{args.version}-chrome-mv3"
    (args.output / f"{stem}.crx").write_bytes(crx)
    (args.output / f"{stem}.zip").write_bytes(payload)
    identifier = extension_id(public_key)
    write_update_manifest(args.output / "updates.xml", manifest, identifier, f"{stem}.crx")
    print(f"Chrome extension ID: {identifier}")


if __name__ == "__main__":
    main()
