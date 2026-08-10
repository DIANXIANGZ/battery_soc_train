from __future__ import annotations

import tempfile
import unittest
import zipfile
from pathlib import Path

from src.data_processing.download_nasa_aging import curl_download_command, extract_nested_archives, extract_verified_zip, sha256_file


class DownloadNasaAgingTests(unittest.TestCase):
    def test_extract_rejects_a_zip_member_that_escapes_destination(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            archive = root / "unsafe.zip"
            with zipfile.ZipFile(archive, "w") as handle:
                handle.writestr("../outside.txt", "unsafe")

            with self.assertRaisesRegex(ValueError, "escapes extraction directory"):
                extract_verified_zip(archive, root / "extracted")

    def test_sha256_file_returns_a_64_character_digest(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            sample = Path(temp_dir) / "sample.bin"
            sample.write_bytes(b"nasa-battery")

            digest = sha256_file(sample)

            self.assertEqual(len(digest), 64)
            self.assertEqual(digest, "f53abc0f280185e9ff25255fd80c12f67e73807ee7b30f5a021f5dd06f79deab")

    def test_extract_nested_archives_unpacks_the_nasa_inner_zip(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            inner = root / "inner.zip"
            with zipfile.ZipFile(inner, "w") as handle:
                handle.writestr("B0005.mat", "fixture")
            outer = root / "outer.zip"
            with zipfile.ZipFile(outer, "w") as handle:
                handle.write(inner, "NASA/BatteryAgingARC-FY08Q4.zip")

            extract_verified_zip(outer, root / "extracted")
            extracted = extract_nested_archives(root / "extracted")

            self.assertEqual(extracted, [root / "extracted" / "NASA" / "BatteryAgingARC-FY08Q4"])
            self.assertEqual((extracted[0] / "B0005.mat").read_text(encoding="utf-8"), "fixture")

    def test_curl_download_command_uses_retries_and_atomic_partial_path(self) -> None:
        command = curl_download_command("https://example.test/data.zip", Path("E:/data.zip.part"))

        self.assertEqual(command[0], "curl.exe")
        self.assertIn("--retry", command)
        self.assertIn("--fail", command)
        self.assertEqual(command[-1], "https://example.test/data.zip")


if __name__ == "__main__":
    unittest.main()
