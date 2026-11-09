import json
from pathlib import Path
import runpy
import subprocess
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from zipfile import ZipFile

updater = runpy.run_path(Path(__file__).with_name("makeepoch-vault-local-updater.py"))
scope = updater["run"].__globals__
EXTENSION_ID = "a" * 32
VERSION = "2026.10.2.2"


class LocalUpdaterTest(unittest.TestCase):
    def setUp(self):
        work = TemporaryDirectory()
        self.addCleanup(work.cleanup)
        self.root = Path(work.name)
        self.key = self.root / "test-key.pem"
        subprocess.run(["openssl", "genrsa", "-out", str(self.key), "2048"], check=True)
        public = subprocess.check_output(["openssl", "pkey", "-in", str(self.key), "-pubout"])
        registration = self.root / "registration"
        registration.mkdir()
        self.directory = self.root / "vault"
        self.directory.mkdir()
        (registration / f"{EXTENSION_ID}.json").write_text(json.dumps({"directory": str(self.directory)}))
        for path, data in self.files("2026.10.2.1").items():
            target = self.directory / path
            target.parent.mkdir(exist_ok=True)
            target.write_text(data)
        self.addCleanup(patch.stopall)
        patch.dict(scope, {"STATE": registration, "PUBLIC_KEY": public}).start()

    @staticmethod
    def files(version):
        return {
            "manifest.json": json.dumps({
                "name": "MakeEpoch Vault",
                "manifest_version": 3,
                "version": version,
                "background": {"service_worker": "background.js"},
                "permissions": ["storage"],
            }),
            "background.js": "",
            "popup/index.html": "<!doctype html>",
            "makeepoch-local.json": '{"channel":"local"}',
        }

    def mock_release(self, files, tamper=False):
        archive = self.root / "fixture.zip"
        with ZipFile(archive, "w") as package:
            for name, content in files.items():
                package.writestr(name, content)
        signature = self.root / "fixture.sig"
        subprocess.run(
            ["openssl", "dgst", "-sha256", "-sign", str(self.key), "-out", str(signature), str(archive)],
            check=True,
        )
        tag = f"makeepoch-v{VERSION}"
        name = f"makeepoch-vault-{VERSION}-chrome-mv3.zip"
        url = f"{updater['RELEASES']}/{tag}/{name}"
        release = {
            "tag_name": tag,
            "assets": [
                {"name": name, "browser_download_url": url},
                {"name": f"{name}.sig", "browser_download_url": f"{url}.sig"},
            ],
        }
        results = {
            updater["API"]: json.dumps(release).encode(),
            url: archive.read_bytes() + (b"tampered" if tamper else b""),
            f"{url}.sig": signature.read_bytes(),
        }
        patch.dict(scope, {"download": lambda address, limit: results[address]}).start()

    def test_update_and_rollback_keep_the_directory(self):
        self.mock_release(self.files(VERSION))
        run = updater["run"]
        self.assertEqual(run(EXTENSION_ID, "stage", "2026.10.2.1"), "ready")
        self.assertEqual(run(EXTENSION_ID, "apply", "2026.10.2.1"), "installed")
        self.assertEqual(updater["manifest"](self.directory)["version"], VERSION)
        self.assertEqual(run(EXTENSION_ID, "status", "2026.10.2.1"), "reload-required")
        self.assertEqual(run(EXTENSION_ID, "rollback"), "rolled-back")
        self.assertEqual(updater["manifest"](self.directory)["version"], "2026.10.2.1")
        self.assertEqual(run(EXTENSION_ID, "stage"), "blocked")

    def test_rejects_tampering_and_signed_unsafe_paths(self):
        self.mock_release(self.files(VERSION), tamper=True)
        with self.assertRaises(subprocess.CalledProcessError):
            updater["run"](EXTENSION_ID, "stage")
        self.mock_release({**self.files(VERSION), "../outside": "invalid"})
        with self.assertRaisesRegex(ValueError, "Unsafe archive"):
            updater["run"](EXTENSION_ID, "stage")
        self.assertEqual(updater["manifest"](self.directory)["version"], "2026.10.2.1")

    def test_rejects_an_update_that_adds_permissions(self):
        files = self.files(VERSION)
        manifest = json.loads(files["manifest.json"])
        manifest["permissions"].append("management")
        files["manifest.json"] = json.dumps(manifest)
        self.mock_release(files)
        with self.assertRaisesRegex(ValueError, "adds Chrome permissions"):
            updater["run"](EXTENSION_ID, "stage")


if __name__ == "__main__":
    unittest.main()
