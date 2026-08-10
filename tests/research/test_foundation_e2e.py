from __future__ import annotations
import json, tempfile, unittest
from pathlib import Path
from src.research.labels import CurrentPoint, online_coulomb_labels
from src.research.pipeline import run_foundation_audit
from src.research.schema import parse_record
from src.research.splits import leave_one_dataset_out

class FoundationEndToEndTests(unittest.TestCase):
    def test_three_dataset_flow_is_reproducible_and_leakage_safe(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp); datasets=[]; rows=[]
            for d in "ABC":
                source=root/d; source.mkdir(); (source/"data.csv").write_text(f"dataset={d}\n",encoding="utf-8")
                datasets.append({"dataset_id":d,"chemistry":"LFP","role":"development" if d=="A" else "frozen_external_test","source_root":str(source),"label_method":"offline_cycle_range"})
                for c in "123":
                    rows.append(parse_record({"dataset_id":d,"cell_id":f"{d}-{c}","session_id":"s","cycle_id":"1","timestamp_s":0,"voltage_v":3.2,"current_a":1,"temperature_c":25,"capacity_ah":1,"soh":.9,"soc_reference":.5,"label_method":"offline_cycle_range","split_role":"development","source_file":"data.csv"}))
            protocol=root/"protocol.json"; registry=root/"datasets.json"
            protocol.write_text(json.dumps({"version":"research_v1","scope":"same_chemistry_cross_dataset","seeds":[11,23,42,67,101],"external_test_locked":True,"minimum_primary_datasets":3}),encoding="utf-8")
            registry.write_text(json.dumps({"datasets":datasets}),encoding="utf-8")
            run_foundation_audit(protocol,registry,root/"first"); run_foundation_audit(protocol,registry,root/"second")
            first=json.loads((root/"first"/"manifest.json").read_text(encoding="utf-8")); second=json.loads((root/"second"/"manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(first,second)
            self.assertEqual(3,len(leave_one_dataset_out(rows)))
            base=(CurrentPoint("A","c","s","1",0,0),CurrentPoint("A","c","s","1",10,1),CurrentPoint("A","c","s","1",20,1))
            changed=base[:-1]+(CurrentPoint("A","c","s","1",20,100),)
            self.assertEqual(online_coulomb_labels(base,.5,2)[:2],online_coulomb_labels(changed,.5,2)[:2])
if __name__=="__main__": unittest.main()
