from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from src.research.manifest import scan_assets, write_manifest
from src.research.protocol import DatasetRegistration


class ManifestTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.source = self.root / "source"
        (self.source / "nested").mkdir(parents=True)
        (self.source / "a.csv").write_bytes(b"alpha")
        (self.source / "nested" / "b.xlsx").write_bytes(b"beta")
        self.registration = DatasetRegistration(
            "A", "LFP", "development", self.source, "offline_cycle_range"
        )

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_scan_is_deterministic_and_hashes_file_contents(self) -> None:
        assets = scan_assets(self.registration)

        self.assertEqual(["a.csv", "nested/b.xlsx"], [x.relative_path for x in assets])
        self.assertEqual(hashlib.sha256(b"alpha").hexdigest(), assets[0].sha256)
        self.assertEqual(5, assets[0].size_bytes)

    def test_scan_rejects_missing_source_root(self) -> None:
        missing = DatasetRegistration(
            "missing", "LFP", "development", self.root / "none", "unknown"
        )
        with self.assertRaises(FileNotFoundError):
            scan_assets(missing)

    def test_manifest_is_json_and_refuses_to_overwrite_existing_output(self) -> None:
        output = self.root / "manifest.json"
        assets = scan_assets(self.registration)
        write_manifest(output, assets)
        payload = json.loads(output.read_text(encoding="utf-8"))
        self.assertEqual("A", payload["assets"][0]["dataset_id"])

        with self.assertRaises(FileExistsError):
            write_manifest(output, ())
        self.assertEqual(2, len(json.loads(output.read_text(encoding="utf-8"))["assets"]))


if __name__ == "__main__":
    unittest.main()
