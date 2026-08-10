"""Download and safely extract the NASA PCoE Battery Data Set."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
from datetime import date
from pathlib import Path
import zipfile

from src.project_paths import DataCenterPaths


NASA_BATTERY_URL = "https://phm-datasets.s3.amazonaws.com/NASA/5.+Battery+Data+Set.zip"


def sha256_file(path: Path) -> str:
    """Return the SHA-256 digest of one file without reading it all at once."""

    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def curl_download_command(url: str, partial_path: Path) -> list[str]:
    """Build the Windows curl command used for retryable binary downloads."""

    return [
        "curl.exe", "-L", "--fail", "--retry", "3", "--retry-delay", "3",
        "--connect-timeout", "30", "--output", str(partial_path), url,
    ]


def extract_verified_zip(archive_path: Path, extract_dir: Path) -> None:
    """Extract a ZIP only when every member stays inside ``extract_dir``."""

    archive_path = Path(archive_path)
    extract_dir = Path(extract_dir)
    target_root = extract_dir.resolve()
    with zipfile.ZipFile(archive_path) as archive:
        for member in archive.infolist():
            target = (target_root / member.filename).resolve()
            if target != target_root and target_root not in target.parents:
                raise ValueError("ZIP member escapes extraction directory.")
        archive.extractall(target_root)


def extract_nested_archives(root: Path) -> list[Path]:
    """Safely unpack the NASA archive's first-level ZIP bundles in place."""

    destinations = []
    for archive_path in sorted(Path(root).rglob("*.zip")):
        destination = archive_path.with_suffix("")
        extract_verified_zip(archive_path, destination)
        destinations.append(destination)
    return destinations


def download_and_extract(url: str, archive_path: Path, extract_dir: Path) -> dict[str, str]:
    """Download a source archive once, extract it safely, and save its provenance."""

    archive_path = Path(archive_path)
    extract_dir = Path(extract_dir)
    archive_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path = archive_path.parent / "download_manifest.json"
    if not archive_path.exists():
        partial_path = archive_path.with_suffix(archive_path.suffix + ".part")
        if partial_path.exists():
            partial_path.unlink()
        subprocess.run(curl_download_command(url, partial_path), check=True)
        os.replace(partial_path, archive_path)

    digest = sha256_file(archive_path)
    extract_verified_zip(archive_path, extract_dir)
    nested_dirs = extract_nested_archives(extract_dir)
    manifest = {
        "source_url": url,
        "download_date": date.today().isoformat(),
        "archive_path": str(archive_path.resolve()),
        "sha256": digest,
        "extract_dir": str(extract_dir.resolve()),
        "nested_extract_dirs": [str(path.resolve()) for path in nested_dirs],
    }
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description="Download NASA PCoE battery aging data.")
    parser.add_argument("--data-root", type=Path, help="Configured SOC data-center root.")
    args = parser.parse_args()
    paths = DataCenterPaths(args.data_root) if args.data_root else DataCenterPaths.from_config()
    raw_dir = paths.nasa_raw_dir
    manifest = download_and_extract(
        NASA_BATTERY_URL,
        raw_dir / "Battery_Data_Set.zip",
        raw_dir / "extracted",
    )
    print(json.dumps(manifest, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
