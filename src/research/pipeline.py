"""First-cycle read-only asset audit for the SOC research program."""
from __future__ import annotations
import argparse, json
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from src.research.manifest import scan_assets
from src.research.protocol import load_dataset_registry, load_protocol

def _atomic(path: Path, payload) -> None:
    temporary=path.with_suffix(path.suffix+".tmp")
    temporary.write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding="utf-8")
    temporary.replace(path)

def _now() -> str: return datetime.now(timezone.utc).isoformat()

def run_foundation_audit(protocol_path: Path, registry_path: Path, output_dir: Path) -> dict:
    output=Path(output_dir)
    if output.exists() and any(output.iterdir()): raise FileExistsError(output)
    output.mkdir(parents=True,exist_ok=True)
    _atomic(output/"status.json",{"state":"running","started_at_utc":_now()})
    try:
        protocol=load_protocol(protocol_path); registrations=load_dataset_registry(registry_path)
        development=next((x for x in registrations if x.role=="development"),None)
        if development is None: raise ValueError("registry requires a development dataset")
        all_assets=[]; quality={}; compatibility={}
        for registration in registrations:
            assets=scan_assets(registration); all_assets.extend(assets); extensions={}
            for asset in assets: extensions[asset.extension]=extensions.get(asset.extension,0)+1
            quality[registration.dataset_id]={"file_count":len(assets),"total_bytes":sum(x.size_bytes for x in assets),"empty_file_count":sum(x.size_bytes==0 for x in assets),"extensions":dict(sorted(extensions.items())),"level":"asset"}
            compatibility[registration.dataset_id]="chemistry_match" if registration.chemistry==development.chemistry else "compatibility_only_chemistry_mismatch"
        _atomic(output/"manifest.json",{"assets":[asdict(x) for x in all_assets]})
        _atomic(output/"quality.json",{"scope":"file_asset_quality_not_sample_quality","datasets":quality})
        _atomic(output/"compatibility.json",{"target_chemistry":development.chemistry,"datasets":compatibility})
        lines=["# 科研基础资产审计","","本报告仅完成文件资产级审计；逐样本质量需在数据源解析后执行。",""]
        lines += [f"- {name}: {data['file_count']} files, {data['total_bytes']} bytes" for name,data in quality.items()]
        (output/"summary.md").write_text("\n".join(lines)+"\n",encoding="utf-8")
        result={"state":"completed","protocol_version":protocol.version,"dataset_count":len(registrations),"asset_count":len(all_assets),"completed_at_utc":_now()}
        _atomic(output/"status.json",result); return result
    except Exception as exc:
        _atomic(output/"status.json",{"state":"failed","error_type":type(exc).__name__,"error":str(exc),"failed_at_utc":_now()}); raise

def main() -> None:
    parser=argparse.ArgumentParser(description="Audit registered SOC research assets without modifying sources.")
    parser.add_argument("--protocol",type=Path,required=True); parser.add_argument("--datasets",type=Path,required=True); parser.add_argument("--output",type=Path,required=True)
    args=parser.parse_args(); print(json.dumps(run_foundation_audit(args.protocol,args.datasets,args.output),ensure_ascii=False,indent=2))
if __name__=="__main__": main()
