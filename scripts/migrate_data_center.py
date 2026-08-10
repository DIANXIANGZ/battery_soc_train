"""Hash-protected migration of SOC data assets out of the code project."""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
import hashlib
import json
from pathlib import Path
import shutil
from typing import Iterable


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_CENTER_ROOT = Path(r"E:\SOC电池数据中心")
MANIFEST_PATH = DATA_CENTER_ROOT / "迁移清单.json"


@dataclass(frozen=True)
class ManifestEntry:
    source: Path
    destination: Path
    size_bytes: int
    sha256: str
    verified: bool = False

    @classmethod
    def from_paths(cls, source: Path, destination: Path) -> "ManifestEntry":
        source = Path(source)
        if not source.is_file():
            raise FileNotFoundError(f"Migration source is not a file: {source}")
        return cls(source, Path(destination), source.stat().st_size, sha256_file(source))


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def copy_and_verify(entries: Iterable[ManifestEntry]) -> list[ManifestEntry]:
    verified_entries: list[ManifestEntry] = []
    for entry in entries:
        entry.destination.parent.mkdir(parents=True, exist_ok=True)
        if entry.destination.exists() and sha256_file(entry.destination) != entry.sha256:
            raise ValueError(f"Destination exists with different content: {entry.destination}")
        if not entry.destination.exists():
            shutil.copy2(entry.source, entry.destination)
        destination_hash = sha256_file(entry.destination)
        if destination_hash != entry.sha256 or entry.destination.stat().st_size != entry.size_bytes:
            raise ValueError(f"Hash verification failed: {entry.destination}")
        verified_entries.append(ManifestEntry(entry.source, entry.destination, entry.size_bytes, entry.sha256, True))
    return verified_entries


def delete_verified_sources(entries: Iterable[ManifestEntry]) -> None:
    entries = list(entries)
    for entry in entries:
        if not entry.verified:
            raise ValueError(f"Refusing to delete unverified source: {entry.source}")
        if not entry.source.is_file() or not entry.destination.is_file():
            raise FileNotFoundError(f"Verified source or destination is missing: {entry.source}")
        if sha256_file(entry.source) != entry.sha256 or sha256_file(entry.destination) != entry.sha256:
            raise ValueError(f"Refusing to delete changed file: {entry.source}")
    for entry in entries:
        entry.source.unlink()


def _files_in(source_root: Path, destination_root: Path) -> list[ManifestEntry]:
    if not source_root.exists():
        return []
    if source_root.is_file():
        return [ManifestEntry.from_paths(source_root, destination_root / source_root.name)]
    return [
        ManifestEntry.from_paths(path, destination_root / path.relative_to(source_root))
        for path in sorted(source_root.rglob("*"))
        if path.is_file()
    ]


def build_manifest(project_root: Path = PROJECT_ROOT, data_center_root: Path = DATA_CENTER_ROOT) -> list[ManifestEntry]:
    project_root = Path(project_root)
    data_center_root = Path(data_center_root)
    entries: list[ManifestEntry] = []
    entries += _files_in(project_root / "data", data_center_root / "02_训练数据" / "01_A123#3_SOC_30秒训练数据")

    results = project_root / "results"
    if results.exists():
        for path in sorted(results.rglob("*")):
            if not path.is_file():
                continue
            relative = path.relative_to(results)
            if relative.parts[0] == "cross_cell_a123_5_part1":
                destination = data_center_root / "03_模型与实验结果" / "02_A123#5_跨电芯评估结果" / Path(*relative.parts[1:])
            else:
                destination = data_center_root / "03_模型与实验结果" / "01_A123#3_基准模型与结果" / relative
            entries.append(ManifestEntry.from_paths(path, destination))

    entries += _files_in(project_root / "platform", data_center_root / "04_训练平台运行记录" / "01_SOC训练平台项目与运行记录")
    entries += _files_in(project_root / "work", data_center_root / "05_外部评估数据" / "03_外部数据清单与处理后样本")
    entries += _files_in(Path(r"E:\Codex\A123_3_part1.zip"), data_center_root / "01_原始数据" / "01_CALCE_A123#3_原始压缩包")
    entries += _files_in(Path(r"E:\Codex\battery_soc_external"), data_center_root / "05_外部评估数据" / "04_历史外部数据归档")
    return entries


def _write_manifest(entries: Iterable[ManifestEntry], path: Path = MANIFEST_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    records = [{**asdict(entry), "source": str(entry.source), "destination": str(entry.destination)} for entry in entries]
    path.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")


def _read_manifest(path: Path = MANIFEST_PATH) -> list[ManifestEntry]:
    records = json.loads(path.read_text(encoding="utf-8"))
    return [ManifestEntry(Path(record["source"]), Path(record["destination"]), record["size_bytes"], record["sha256"], record["verified"]) for record in records]


def _remove_empty_directories(roots: Iterable[Path]) -> None:
    for root in roots:
        if root.is_dir():
            for directory in sorted((path for path in root.rglob("*") if path.is_dir()), reverse=True):
                try:
                    directory.rmdir()
                except OSError:
                    pass
            try:
                root.rmdir()
            except OSError:
                pass


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=("plan", "copy", "delete"), required=True)
    args = parser.parse_args()
    if args.mode == "plan":
        entries = build_manifest()
        _write_manifest(entries)
        print(f"Planned {len(entries)} files in {MANIFEST_PATH}")
    elif args.mode == "copy":
        entries = _read_manifest()
        verified = copy_and_verify(entries)
        _write_manifest(verified)
        print(f"Verified {len(verified)} files")
    else:
        entries = _read_manifest()
        delete_verified_sources(entries)
        _remove_empty_directories((PROJECT_ROOT / "data", PROJECT_ROOT / "results", PROJECT_ROOT / "platform", PROJECT_ROOT / "work", Path(r"E:\Codex\battery_soc_external")))
        print(f"Deleted {len(entries)} verified source files")


if __name__ == "__main__":
    main()
