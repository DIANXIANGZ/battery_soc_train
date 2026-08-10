from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from src.research.protocol import load_dataset_registry, load_protocol


class ResearchProtocolTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.protocol_path = self.root / "protocol.json"
        self.registry_path = self.root / "datasets.json"
        self.valid_payload = {
            "version": "research_v1",
            "scope": "same_chemistry_cross_dataset",
            "seeds": [11, 23, 42, 67, 101],
            "external_test_locked": True,
            "minimum_primary_datasets": 3,
        }
        self.protocol_path.write_text(
            json.dumps(self.valid_payload), encoding="utf-8"
        )
        self.registry_path.write_text(
            json.dumps(
                {
                    "datasets": [
                        {
                            "dataset_id": "A123#3",
                            "chemistry": "LFP",
                            "role": "development",
                            "source_root": str(self.root / "a123_3"),
                            "label_method": "offline_cycle_range",
                        },
                        {
                            "dataset_id": "A123#5",
                            "chemistry": "LFP",
                            "role": "frozen_external_test",
                            "source_root": str(self.root / "a123_5"),
                            "label_method": "offline_cycle_range",
                        },
                        {
                            "dataset_id": "CX2_4",
                            "chemistry": "LCO",
                            "role": "compatibility_audit",
                            "source_root": str(self.root / "cx2_4"),
                            "label_method": "source_defined",
                        },
                    ]
                }
            ),
            encoding="utf-8",
        )

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _write_protocol(self, payload: dict) -> Path:
        path = self.root / "invalid_protocol.json"
        path.write_text(json.dumps(payload), encoding="utf-8")
        return path

    def test_protocol_loads_frozen_scope_and_unique_seeds(self) -> None:
        protocol = load_protocol(self.protocol_path)

        self.assertEqual("same_chemistry_cross_dataset", protocol.scope)
        self.assertEqual((11, 23, 42, 67, 101), protocol.seeds)
        self.assertTrue(protocol.external_test_locked)
        self.assertEqual(3, protocol.minimum_primary_datasets)

    def test_protocol_rejects_duplicate_seeds_and_unlocked_external_test(self) -> None:
        payload = self.valid_payload | {
            "seeds": [11, 11],
            "external_test_locked": False,
        }

        with self.assertRaisesRegex(ValueError, "unique.*external"):
            load_protocol(self._write_protocol(payload))

    def test_dataset_registry_assigns_each_dataset_one_role(self) -> None:
        records = load_dataset_registry(self.registry_path)

        self.assertEqual(
            {"A123#3", "A123#5", "CX2_4"},
            {item.dataset_id for item in records},
        )
        cx2 = next(item for item in records if item.dataset_id == "CX2_4")
        self.assertEqual("compatibility_audit", cx2.role)

    def test_dataset_registry_rejects_duplicate_ids(self) -> None:
        payload = json.loads(self.registry_path.read_text(encoding="utf-8"))
        payload["datasets"].append(dict(payload["datasets"][0]))
        self.registry_path.write_text(json.dumps(payload), encoding="utf-8")

        with self.assertRaisesRegex(ValueError, "dataset_id.*unique"):
            load_dataset_registry(self.registry_path)


if __name__ == "__main__":
    unittest.main()
