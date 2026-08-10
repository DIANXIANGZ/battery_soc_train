from __future__ import annotations
import json, tempfile, unittest
from pathlib import Path
from src.research.pipeline import run_foundation_audit

class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.root=Path(self.temp.name); datasets=[]
        for name,chem,role in (("A","LFP","development"),("B","LFP","frozen_external_test"),("C","LCO","compatibility_audit")):
            source=self.root/name; source.mkdir(); (source/"data.csv").write_text(name,encoding="utf-8")
            datasets.append({"dataset_id":name,"chemistry":chem,"role":role,"source_root":str(source),"label_method":"offline_cycle_range"})
        self.protocol=self.root/"protocol.json"; self.registry=self.root/"datasets.json"; self.output=self.root/"output"
        self.protocol.write_text(json.dumps({"version":"research_v1","scope":"same_chemistry_cross_dataset","seeds":[11,23,42,67,101],"external_test_locked":True,"minimum_primary_datasets":3}),encoding="utf-8")
        self.registry.write_text(json.dumps({"datasets":datasets}),encoding="utf-8")
    def tearDown(self): self.temp.cleanup()
    def test_audit_writes_complete_traceable_artifacts(self):
        result=run_foundation_audit(self.protocol,self.registry,self.output)
        self.assertEqual("completed",result["state"])
        self.assertEqual({"manifest.json","quality.json","compatibility.json","summary.md","status.json"},{x.name for x in self.output.iterdir()})
        self.assertTrue(json.loads((self.output/"status.json").read_text(encoding="utf-8"))["completed_at_utc"])
    def test_audit_refuses_nonempty_output(self):
        self.output.mkdir(); (self.output/"user.txt").write_text("keep",encoding="utf-8")
        with self.assertRaises(FileExistsError): run_foundation_audit(self.protocol,self.registry,self.output)
if __name__=="__main__": unittest.main()
