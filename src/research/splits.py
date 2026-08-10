"""Deterministic dataset- and cell-level research folds."""
from __future__ import annotations
from dataclasses import dataclass
from src.research.leakage import assert_disjoint_domains
from src.research.schema import SampleRecord

@dataclass(frozen=True)
class DomainFold:
    fold_id: str
    test_domain: str
    validation_domain: str
    train: tuple[SampleRecord,...]
    validation: tuple[SampleRecord,...]
    test: tuple[SampleRecord,...]

def _ordered(records): return tuple(sorted(records,key=lambda r:r.key))

def _folds(records, domain_fn, prefix):
    rows=_ordered(records); domains=sorted({domain_fn(x) for x in rows})
    if len(domains)<3: raise ValueError("domain splitting requires at least three domains")
    result=[]
    for index,test_domain in enumerate(domains):
        validation_domain=domains[(index-1)%len(domains)]
        test=tuple(x for x in rows if domain_fn(x)==test_domain)
        validation=tuple(x for x in rows if domain_fn(x)==validation_domain)
        train=tuple(x for x in rows if domain_fn(x) not in (test_domain,validation_domain))
        assert_disjoint_domains(train,validation,test)
        result.append(DomainFold(f"{prefix}-{index+1:02d}",test_domain,validation_domain,train,validation,test))
    return tuple(result)

def leave_one_dataset_out(records): return _folds(records,lambda x:x.key.dataset_id,"lodo")
def leave_one_cell_out(records): return _folds(records,lambda x:x.key.cell_id,"loco")
