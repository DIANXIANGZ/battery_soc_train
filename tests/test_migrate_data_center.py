from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest


PROJECT = Path(__file__).resolve().parents[1]
MODULE_PATH = PROJECT / "scripts" / "migrate_data_center.py"
SPEC = importlib.util.spec_from_file_location("migrate_data_center", MODULE_PATH)
migrate_data_center = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = migrate_data_center
SPEC.loader.exec_module(migrate_data_center)

ManifestEntry = migrate_data_center.ManifestEntry
copy_and_verify = migrate_data_center.copy_and_verify
delete_verified_sources = migrate_data_center.delete_verified_sources


class DataCenterMigrationTests(unittest.TestCase):
    def test_copy_and_verify_preserves_bytes_and_sha256(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = root / "source.bin"
            destination = root / "destination.bin"
            source.write_bytes(b"soc-data")

            verified = copy_and_verify([ManifestEntry.from_paths(source, destination)])

            self.assertTrue(verified[0].verified)
            self.assertEqual(source.read_bytes(), destination.read_bytes())
            self.assertEqual(verified[0].sha256, migrate_data_center.sha256_file(destination))

    def test_delete_verified_sources_rejects_unverified_entry(self) -> None:
        entry = ManifestEntry(Path("source"), Path("destination"), 0, "", False)

        with self.assertRaisesRegex(ValueError, "unverified"):
            delete_verified_sources([entry])


if __name__ == "__main__":
    unittest.main()
