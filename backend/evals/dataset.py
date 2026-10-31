"""Local content-addressed dataset loader; references are never model-visible."""
import json
from pathlib import Path
from .contracts import Case, digest

DATA = Path(__file__).parent/'datasets'


def read_json(path):
    result=json.loads(Path(path).read_text(encoding='utf-8'),parse_constant=lambda v:(_ for _ in ()).throw(ValueError('nonfinite JSON')))
    digest(result)  # Also reject numeric overflow such as 1e999.
    return result


def asset(path, root=DATA):
    target=(root/path).resolve()
    if not target.is_relative_to(root.resolve()):
        raise ValueError('asset outside dataset')
    return read_json(target)


def load_case(case_id, root=DATA):
    if case_id not in {f'T{i:02d}' for i in range(1,19)} | {f'R{i:02d}' for i in range(1,13)}:
        raise ValueError('unknown case id')
    case=Case.model_validate(asset(f'cases/{case_id}.json',root))
    inputs=asset(case.input_path,root);reference=asset(case.reference_path,root)
    routes=asset(case.route_path,root) if case.route_path else None
    if digest(inputs)!=case.input_sha256 or digest(reference)!=case.reference_sha256 or (routes is not None and digest(routes)!=case.route_sha256):
        raise ValueError('frozen asset hash mismatch; version and review required')
    return case,inputs,reference,routes


def load_all(root=DATA):
    return [load_case(f'{prefix}{i:02d}',root) for prefix,n in [('T',18),('R',12)] for i in range(1,n+1)]


def model_inputs(case_id, *, eligible_ids=None, root=DATA):
    """Ticket filtering must come from the observed system, never the reference gold set."""
    case,inputs,_,_=load_case(case_id,root)
    if case.target=='ticket_recommendation':
        if eligible_ids is None:
            raise ValueError('supply system-observed eligible IDs, not reference IDs')
        candidates={c['id']:c for c in inputs['candidates']}
        if len(eligible_ids)!=len(set(eligible_ids)) or not set(eligible_ids)<=candidates.keys():
            raise ValueError('invalid observed candidate set')
        return {'query':inputs['query'],'candidates':[candidates[k] for k in eligible_ids]}
    return {k:inputs[k] for k in ('request','day_detail','dining_candidates','hint')}
