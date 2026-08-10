"""Deterministic, read-only asset manifests for research datasets."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
from pathlib import Path
from typing import Sequence

from src.research.protocol import DatasetRegistration


@dataclass(frozen=True)
class FileAsset:
    dataset_id: str
    relative_path: str
    size_bytes: int
    sha256: str
    extension: str


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def scan_assets(dataset: DatasetRegistration) -> tuple[FileAsset, ...]:
    root = dataset.source_root.resolve()
    if not root.is_dir():
        raise FileNotFoundError(root)
    files = sorted(
        (path for path in root.rglob("*") if path.is_file()),
        key=lambda path: path.relative_to(root).as_posix(),
    )
    return tuple(
        FileAsset(
            dataset_id=dataset.dataset_id,
            relative_path=path.relative_to(root).as_posix(),
            size_bytes=path.stat().st_size,
            sha256=sha256_file(path),
            extension=path.suffix.lower(),
        )
        for path in files
    )


def write_manifest(path: Path, assets: Sequence[FileAsset]) -> None:
    path = Path(path)
    if path.exists():
        raise FileExistsError(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    payload = {"assets": [asdict(asset) for asset in assets]}
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    temporary.replace(path)

