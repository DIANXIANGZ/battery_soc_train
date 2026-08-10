from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from unittest import mock
from pathlib import Path

from src.data_processing.download_public_batteries import (
    PublicBatterySource,
    download_source,
    load_sources,
    validate_source,
)
from src.project_paths import DataCenterPaths


class PublicBatteryDownloadTests(unittest.TestCase):
    def test_public_battery_paths_are_isolated(self) -> None:
        paths = DataCenterPaths(Path("/data"))
        self.assertEqual(paths.public_battery_raw_dir, Path("/data/01_原始数据/04_公开电池数据集"))
        self.assertNotEqual(paths.public_battery_raw_dir, paths.nasa_raw_dir)

    def test_source_rejects_non_https_downloads(self) -> None:
        source = PublicBatterySource("unsafe", "https://example.test", ("file:///tmp/data.zip",), "unknown", ("soh",), None)
        with self.assertRaisesRegex(ValueError, "HTTPS"):
            validate_source(source)

    def test_existing_verified_archive_is_reused_and_manifested(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            folder = root / "sample"
            folder.mkdir()
            archive = folder / "data.zip"
            archive.write_bytes(b"verified-battery-data")
            digest = hashlib.sha256(archive.read_bytes()).hexdigest()
            source = PublicBatterySource(
                "sample", "https://example.test/dataset", ("https://example.test/data.zip",),
                "research-use", ("soc", "soh"), digest,
            )

            result = download_source(source, root)

            self.assertTrue(result["reused"])
            manifest = json.loads((folder / "download_manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["sha256"], digest)
            self.assertEqual(manifest["landing_page"], source.landing_page)
            self.assertEqual(manifest["license"], "research-use")

    def test_partial_file_is_never_treated_as_verified_archive(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            folder = root / "sample"
            folder.mkdir()
            (folder / "data.zip.part").write_bytes(b"incomplete")
            source = PublicBatterySource(
                "sample", "https://example.test/dataset", ("https://example.test/data.zip",),
                "research-use", ("soc",), hashlib.sha256(b"incomplete").hexdigest(),
            )
            with mock.patch("subprocess.run", side_effect=RuntimeError("network disabled")):
                with self.assertRaisesRegex(RuntimeError, "network disabled"):
                    download_source(source, root)
            self.assertFalse((folder / "data.zip").exists())
            self.assertTrue((folder / "data.zip.part").exists())

    def test_source_config_requires_version_and_ignores_candidates(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            config = Path(temp_dir) / "sources.json"
            config.write_text(json.dumps({
                "manifest_version": 1,
                "sources": [
                    {
                        "source_id": "active",
                        "status": "approved",
                        "version": "2026-01",
                        "landing_page": "https://example.test/active",
                        "download_urls": ["https://example.test/data.zip"],
                        "license": "research-use",
                        "targets": ["soh"],
                        "checksum": None,
                    },
                    {
                        "source_id": "pending",
                        "status": "candidate",
                        "version": None,
                        "landing_page": "https://example.test/pending",
                        "download_urls": [],
                        "license": "unverified",
                        "targets": ["rul"],
                        "checksum": None,
                    },
                ],
            }), encoding="utf-8")

            sources = load_sources(config)

            self.assertEqual([source.source_id for source in sources], ["active"])


if __name__ == "__main__":
    unittest.main()
