#!/usr/bin/env python3
"""Install and run the native updater for MakeEpoch Vault's unpacked Chrome build."""

import argparse
import base64
import fcntl
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shlex
import shutil
import stat
import struct
import subprocess
import sys
from tempfile import TemporaryDirectory
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener
from zipfile import ZipFile

HOST = "com.makeepoch.vault_updater"
REPO = "MakeEpoch/bitwarden-clients"
RELEASES = f"https://github.com/{REPO}/releases/download"
API = f"https://api.github.com/repos/{REPO}/releases/latest"
PUBLIC_KEY = b""  # Replaced by the release packager.
STATE = Path.home() / ".local/share/makeepoch-vault/local"
CHANNEL = "makeepoch-local.json"
MAX_ZIP = 64 * 1024 * 1024


def version_parts(value):
    if not isinstance(value, str) or not re.fullmatch(r"(?:0|[1-9][0-9]{0,4})(?:\.(?:0|[1-9][0-9]{0,4})){0,3}", value):
        raise ValueError("Invalid extension version")
    parts = [int(part) for part in value.split(".")]
    if not any(parts) or max(parts) > 65535:
        raise ValueError("Invalid extension version")
    return tuple(parts + [0] * (4 - len(parts)))


def manifest(directory):
    if not directory.is_dir() or directory.is_symlink() or directory.resolve() != directory:
        raise ValueError("The unpacked extension must use a real, fixed directory")
    if (directory / ".git").exists():
        raise ValueError("Select the unpacked installation directory, not a source checkout")
    entry = directory / "manifest.json"
    if entry.is_symlink():
        raise ValueError("Unexpected manifest symlink")
    data = json.loads(entry.read_bytes())
    if (
        data.get("name") != "MakeEpoch Vault" or data.get("manifest_version") != 3
        or data.get("background", {}).get("service_worker") != "background.js"
        or not (directory / "background.js").is_file()
        or not (directory / "popup/index.html").is_file()
    ):
        raise ValueError("Not a MakeEpoch Vault Chrome installation")
    version_parts(data["version"])
    return data


def validate_id(extension_id, data):
    if not re.fullmatch(r"[a-p]{32}", extension_id):
        raise ValueError("Use the extension ID shown in chrome://extensions")
    if "key" in data:
        digest = hashlib.sha256(base64.b64decode(data["key"], validate=True)).hexdigest()[:32]
        if digest.translate(str.maketrans("0123456789abcdef", "abcdefghijklmnop")) != extension_id:
            raise ValueError("The directory manifest belongs to a different extension ID")


def install(directory, extension_id):
    validate_id(extension_id, manifest(directory))
    if sys.platform == "darwin":
        chrome = Path.home() / "Library/Application Support/Google/Chrome"
    elif sys.platform.startswith("linux"):
        chrome = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "google-chrome"
    else:
        raise ValueError("This installer supports Google Chrome on Linux and macOS")

    entry = STATE / f"{extension_id}.json"
    if entry.exists() and Path(json.loads(entry.read_bytes())["directory"]) != directory:
        raise ValueError("This extension ID is already registered to a different directory")
    STATE.mkdir(parents=True, exist_ok=True)
    entry.write_text(json.dumps({"directory": str(directory)}))
    updater = STATE / "updater.py"
    source = Path(__file__).resolve()
    if source != updater.resolve():
        shutil.copyfile(source, updater)
    launcher = STATE / "run"
    launcher.write_text(f"#!/bin/sh\nexec {shlex.quote(sys.executable)} {shlex.quote(str(updater))} \"$@\"\n")
    launcher.chmod(0o700)
    origins = [f"chrome-extension://{p.stem}/" for p in STATE.glob("*.json") if re.fullmatch(r"[a-p]{32}", p.stem)]
    hosts = chrome / "NativeMessagingHosts"
    hosts.mkdir(parents=True, exist_ok=True)
    (hosts / f"{HOST}.json").write_text(json.dumps({
        "name": HOST,
        "description": "MakeEpoch Vault local updater",
        "path": str(launcher),
        "type": "stdio",
        "allowed_origins": sorted(origins),
    }))


class ReleaseRedirects(HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, message, headers, newurl):
        url = urlsplit(newurl)
        if url.scheme != "https" or url.hostname not in {
            "github.com", "release-assets.githubusercontent.com", "objects.githubusercontent.com",
        } or url.username or url.password or url.port:
            raise ValueError("Unexpected GitHub release redirect")
        return super().redirect_request(request, fp, code, message, headers, newurl)


def download(url, limit):
    request = Request(url, headers={"User-Agent": "MakeEpoch-Vault-local-updater"})
    with build_opener(ReleaseRedirects).open(request, timeout=25) as response:
        data = response.read(limit + 1)
    if len(data) > limit:
        raise ValueError("Release download exceeds the size limit")
    return data


def unpack_verified(archive, signature, target):
    with TemporaryDirectory(dir=target.parent) as work:
        files = Path(work)
        (files / "key.pem").write_bytes(PUBLIC_KEY)
        (files / "archive.zip").write_bytes(archive)
        (files / "archive.sig").write_bytes(signature)
        subprocess.run(
            ["openssl", "dgst", "-sha256", "-verify", str(files / "key.pem"),
             "-signature", str(files / "archive.sig"), str(files / "archive.zip")],
            check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        with ZipFile(files / "archive.zip") as package:
            members = package.infolist()
            if len(members) > 4000 or sum(entry.file_size for entry in members) > 300 * 1024 * 1024:
                raise ValueError("Unexpected archive size")
            seen = set()
            for entry in members:
                name = entry.filename
                path = PurePosixPath(name)
                mode = stat.S_IFMT(entry.external_attr >> 16)
                if (
                    not path.parts or name.startswith("/") or "\\" in name or ":" in name
                    or ".." in path.parts or path.as_posix().casefold() in seen
                    or mode not in (0, stat.S_IFDIR, stat.S_IFREG)
                ):
                    raise ValueError("Unsafe archive entry")
                seen.add(path.as_posix().casefold())
            package.extractall(target)


def stage(state, current):
    release = json.loads(download(API, 1024 * 1024))
    tag = release["tag_name"]
    if not tag.startswith("makeepoch-v"):
        return "current"
    version = tag.removeprefix("makeepoch-v")
    if version_parts(version) <= version_parts(current["version"]):
        return "current"
    blocked = state / "blocked"
    if blocked.exists() and blocked.read_text() == version:
        return "blocked"
    name = f"makeepoch-vault-{version}-chrome-mv3.zip"
    assets = {asset["name"]: asset["browser_download_url"] for asset in release["assets"]}
    url = f"{RELEASES}/{tag}/{name}"
    if assets.get(name) != url or assets.get(f"{name}.sig") != f"{url}.sig":
        return "no-local-package"
    staged = state / "staged"
    if staged.exists() and manifest(staged)["version"] == version:
        return "ready"

    archive = download(url, MAX_ZIP)
    signature = download(f"{url}.sig", 4096)
    with TemporaryDirectory(dir=state) as work:
        target = Path(work) / "extension"
        unpack_verified(archive, signature, target)
        data = manifest(target)
        if data["version"] != version or json.loads((target / CHANNEL).read_bytes()) != {"channel": "local"}:
            raise ValueError("Signed package metadata does not match its release")
        if "key" in data or "update_url" in data:
            raise ValueError("Expected an unpacked local package")
        for permission in ("permissions", "optional_permissions", "host_permissions", "optional_host_permissions"):
            if not set(data.get(permission, [])).issubset(current.get(permission, [])):
                raise ValueError("The update adds Chrome permissions and needs a manual install")
        # An older signed ZIP loaded unpacked may already have a key. Preserve
        # that identity as well as path-derived IDs from unsigned unpacked builds.
        if "key" in current:
            data["key"] = current["key"]
            (target / "manifest.json").write_text(json.dumps(data, indent=2) + "\n")
        if staged.exists():
            shutil.rmtree(staged)
        target.rename(staged)
    return "ready"


def apply(directory, state, current):
    staged, backup = (state / name for name in ("staged", "backup"))
    next_data = manifest(staged)
    if version_parts(next_data["version"]) <= version_parts(current["version"]):
        return "current"
    if next_data.get("key") != current.get("key"):
        raise ValueError("An update cannot change the extension identity")
    if backup.exists():
        shutil.rmtree(backup)
    directory.rename(backup)
    try:
        staged.rename(directory)
    except OSError:
        backup.rename(directory)
        raise
    return "installed"


def run(extension_id, operation, running_version=None):
    if not re.fullmatch(r"[a-p]{32}", extension_id):
        raise ValueError("Invalid extension ID")
    directory = Path(json.loads((STATE / f"{extension_id}.json").read_bytes())["directory"])
    state = directory.parent / f".makeepoch-vault-{extension_id}-{hashlib.sha256(os.fsencode(directory)).hexdigest()[:12]}"
    state.mkdir(mode=0o700, exist_ok=True)
    if state.is_symlink() or state.stat().st_uid != os.getuid() or state.stat().st_mode & 0o077:
        raise ValueError("Unsafe updater working directory")
    with (state / "lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        backup = state / "backup"
        if not directory.exists() and backup.exists():
            validate_id(extension_id, manifest(backup))
            backup.rename(directory)
        current = manifest(directory)
        validate_id(extension_id, current)
        if running_version is not None and current["version"] != running_version:
            return "reload-required"
        if operation == "status":
            return "connected"
        if operation == "rollback":
            validate_id(extension_id, manifest(backup))
            failed = state / "failed"
            if failed.exists():
                shutil.rmtree(failed)
            directory.rename(failed)
            try:
                backup.rename(directory)
            except OSError:
                failed.rename(directory)
                raise
            (state / "blocked").write_text(current["version"])
            shutil.rmtree(failed)
            return "rolled-back"
        if operation == "apply":
            return apply(directory, state, current)
        result = stage(state, current)
        if operation == "update" and result == "ready":
            return apply(directory, state, current)
        return result


def native(origin):
    origin_match = re.fullmatch(r"chrome-extension://([a-p]{32})/", origin)
    if not origin_match:
        raise ValueError("Invalid Chrome native messaging origin")
    stream = sys.stdin.buffer
    size = struct.unpack("=I", stream.read(4))[0]
    if not 0 < size <= 4096:
        raise ValueError("Invalid native message size")
    request = json.loads(stream.read(size))
    operation = request.get("operation")
    if operation not in {"status", "stage", "apply"}:
        raise ValueError("Unsupported native update operation")
    version_parts(request.get("version"))
    try:
        result = {"ok": True, "state": run(origin_match[1], operation, request["version"])}
    except (OSError, ValueError, KeyError, subprocess.CalledProcessError) as error:
        result = {"ok": False, "error": str(error)}
    response = json.dumps(result).encode()
    sys.stdout.buffer.write(struct.pack("=I", len(response)) + response)
    sys.stdout.buffer.flush()


def main():
    if not PUBLIC_KEY:
        raise ValueError("Use the local updater asset published on GitHub Releases")
    os.umask(0o077)
    if len(sys.argv) > 1 and sys.argv[1].startswith("chrome-extension://"):
        native(sys.argv[1])
        return
    parser = argparse.ArgumentParser(description=__doc__)
    actions = parser.add_subparsers(dest="operation", required=True)
    setup = actions.add_parser("install")
    setup.add_argument("directory", type=Path)
    setup.add_argument("extension_id")
    for operation in ("update", "rollback"):
        actions.add_parser(operation).add_argument("extension_id")
    args = parser.parse_args()
    if args.operation == "install":
        install(Path(os.path.abspath(args.directory.expanduser())), args.extension_id)
        print("Local updater registered")
    else:
        print(run(args.extension_id, args.operation))


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, KeyError, subprocess.CalledProcessError) as error:
        sys.exit(str(error))
