"""Reproducible downloader for approved public battery datasets."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
from urllib.parse import unquote, urlparse


_SOURCE_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_-]*$")


@dataclass(frozen=True)
class PublicBatterySource:
    """Metadata required to download and audit one public source."""

    source_id: str
    landing_page: str
    download_urls: tuple[str, ...]
    license: str
    targets: tuple[str, ...]
    checksum: str | None = None
    version: str = "unspecified"


def validate_source(source: PublicBatterySource) -> None:
    """Reject incomplete or unsafe source definitions before touching disk."""

    if not _SOURCE_ID_PATTERN.fullmatch(source.source_id):
        raise ValueError("source_id must be a lowercase safe slug")
    if urlparse(source.landing_page).scheme != "https":
        raise ValueError("Landing page must use HTTPS")
    if not source.download_urls:
        raise ValueError("At least one download URL is required")
    if any(urlparse(url).scheme != "https" for url in source.download_urls):
        raise ValueError("All download URLs must use HTTPS")
    if not source.license.strip():
        raise ValueError("A non-empty license statement is required")
    if not source.targets or any(not target.strip() for target in source.targets):
        raise ValueError("At least one non-empty prediction target is required")
    if source.checksum is not None and not re.fullmatch(r"[0-9a-fA-F]{64}", source.checksum):
        raise ValueError("checksum must be a SHA-256 hexadecimal digest")
    if not source.version.strip():
        raise ValueError("A non-empty source version is required")


def load_sources(config_path: Path) -> list[PublicBatterySource]:
    """Load only sources whose provenance has been approved."""

    payload = json.loads(config_path.read_text(encoding="utf-8"))
    if payload.get("manifest_version") != 1:
        raise ValueError("Unsupported public battery source manifest version")
    sources: list[PublicBatterySource] = []
    for item in payload.get("sources", []):
        if item.get("status") != "approved":
            continue
        source = PublicBatterySource(
            source_id=item["source_id"],
            landing_page=item["landing_page"],
            download_urls=tuple(item["download_urls"]),
            license=item["license"],
            targets=tuple(item["targets"]),
            checksum=item.get("checksum"),
            version=item["version"],
        )
        validate_source(source)
        sources.append(source)
    return sources


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _archive_name(url: str) -> str:
    name = Path(unquote(urlparse(url).path)).name
    return name or "data.bin"


def _write_manifest(source: PublicBatterySource, archive: Path, digest: str, reused: bool) -> dict[str, object]:
    payload: dict[str, object] = {
        "source_id": source.source_id,
        "landing_page": source.landing_page,
        "source_url": source.download_urls[0],
        "version": source.version,
        "license": source.license,
        "targets": list(source.targets),
        "sha256": digest,
        "byte_count": archive.stat().st_size,
        "archive_path": str(archive),
        "reused": reused,
        "downloaded_at_utc": datetime.now(timezone.utc).isoformat(),
    }
    manifest_path = archive.parent / "download_manifest.json"
    manifest_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload


def download_source(source: PublicBatterySource, raw_root: Path) -> dict[str, object]:
    """Download one source atomically, verify it, and persist provenance."""

    validate_source(source)
    source_dir = raw_root / source.source_id
    source_dir.mkdir(parents=True, exist_ok=True)
    archive = source_dir / _archive_name(source.download_urls[0])

    if archive.is_file():
        digest = sha256_file(archive)
        if source.checksum is None or digest.lower() == source.checksum.lower():
            return _write_manifest(source, archive, digest, reused=True)

    partial = archive.with_name(f"{archive.name}.part")
    command = [
        "curl", "-L", "--fail", "--retry", "5", "--retry-all-errors", "--retry-delay", "2",
        "--connect-timeout", "30", "--continue-at", "-",
        "--output", str(partial), source.download_urls[0],
    ]
    try:
        subprocess.run(command, check=True)
        digest = sha256_file(partial)
        if source.checksum is not None and digest.lower() != source.checksum.lower():
            partial.unlink(missing_ok=True)
            raise ValueError(f"SHA-256 mismatch for {source.source_id}")
        partial.replace(archive)
    except Exception:
        raise
    return _write_manifest(source, archive, digest, reused=False)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--raw-root", type=Path, required=True)
    args = parser.parse_args(argv)
    for source in load_sources(args.config):
        result = download_source(source, args.raw_root)
        print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
