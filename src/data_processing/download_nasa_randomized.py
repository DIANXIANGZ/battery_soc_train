"""Download NASA's randomized battery-usage archives with provenance."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from src.data_processing.download_nasa_aging import download_and_extract
from src.project_paths import DataCenterPaths


_BASE = "https://zenodo.org/records/15277374/files/"
RANDOMIZED_ARCHIVES = (
    {"name": "01_uniform_charge_discharge", "filename": "1. Battery_Uniform_Distribution_Charge_Discharge_DataSet_2Post.zip", "official_md5": "4c140b2223fbd31c5f17f6c4ff470d9e"},
    {"name": "02_uniform_discharge_room", "filename": "2. Battery_Uniform_Distribution_Discharge_Room_Temp_DataSet_2Post.zip", "official_md5": "aa53dce833e0ce7ee75376846dec4e59"},
    {"name": "03_uniform_variable_charge", "filename": "3. Battery_Uniform_Distribution_Variable_Charge_Room_Temp_DataSet_2Post.zip", "official_md5": "f7a4bd5502895073f362f09327b323af"},
    {"name": "04_skewed_high_40c", "filename": "4. RW_Skewed_High_40C_DataSet_2Post.zip", "official_md5": "b871415f3dc1da96f0f8848e66162767"},
    {"name": "05_skewed_high_room", "filename": "5. RW_Skewed_High_Room_Temp_DataSet_2Post.zip", "official_md5": "9a0fabc687ae3a8d990c9d6f2f0412d4"},
    {"name": "06_skewed_low_40c", "filename": "6. RW_Skewed_Low_40C_DataSet_2Post.zip", "official_md5": "120d9f075fcd3672d76ac625324234f8"},
    {"name": "07_skewed_low_room", "filename": "7. RW_Skewed_Low_Room_Temp_DataSet_2Post.zip", "official_md5": "14130c74dd2caa3c6fbda83df26eb55d"},
)
RANDOMIZED_ARCHIVES = tuple({**item, "url": _BASE + item["filename"].replace(" ", "%20") + "?download=1"} for item in RANDOMIZED_ARCHIVES)


def md5_file(path: Path) -> str:
    digest = hashlib.md5()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def download_randomized_archives(data_root: Path) -> list[dict[str, str]]:
    root = DataCenterPaths(data_root).nasa_raw_dir / "randomized"
    completed = []
    for item in RANDOMIZED_ARCHIVES:
        folder = root / item["name"]
        manifest = download_and_extract(item["url"], folder / item["filename"], folder / "extracted")
        actual_md5 = md5_file(folder / item["filename"])
        if actual_md5 != item["official_md5"]:
            raise ValueError(f"Official MD5 does not match for {item['filename']}")
        manifest["official_md5"] = item["official_md5"]
        manifest["actual_md5"] = actual_md5
        (folder / "download_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        completed.append(manifest)
    return completed


def main() -> None:
    parser = argparse.ArgumentParser(description="Download NASA randomized battery data.")
    parser.add_argument("--data-root", type=Path, help="Configured SOC data-center root.")
    args = parser.parse_args()
    root = args.data_root or DataCenterPaths.from_config().root
    for manifest in download_randomized_archives(root):
        print(json.dumps(manifest, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
