"""Dataset integrity, source lineage and route coverage without business services."""
from collections import Counter,defaultdict
import hashlib
import itertools
from .contracts import RULES, digest
from .dataset import DATA, asset, load_all


def validate(root=DATA):
    manifest=asset('manifest.json',root)
    for path,sha in manifest['files'].items():
        asset(path,root)  # Path containment and strict JSON, before reading bytes.
        if hashlib.sha256((root/path).read_bytes()).hexdigest()!=sha:raise ValueError('manifest file hash mismatch: '+path)
    if digest(manifest['files'])!=manifest['content_sha256']:raise ValueError('manifest digest mismatch')
    bundles=load_all(root);cases=[c for c,*_ in bundles]
    if set(manifest['case_ids'])!={c.case_id for c in cases} or len(manifest['case_ids'])!=30:raise ValueError('case inventory mismatch')
    splits=Counter(c.split for c in cases);modes=Counter(c.execution_mode for c in cases)
    if splits!={'dev':20,'holdout':10} or modes!={'live_model_with_replay':20,'injected_failure':8,'no_model':2}:raise ValueError('frozen scenario counts changed')
    covered={a.rule_id for c in cases for a in c.expected_assertions if a.applicable}
    if covered!=set(RULES):raise ValueError('missing rule coverage')
    route_audit={}
    families=defaultdict(set)
    for c,inp,ref,routes in bundles:
        families[c.family].add(c.split)
        if not c.sources or not c.annotation.rationale:raise ValueError('missing provenance/annotation')
        if c.data_origin=='synthetic' and any(s['origin']!='synthetic' for s in c.sources):raise ValueError('synthetic source misclassified')
        if c.data_origin!='synthetic' and not {'historical_capture','new_capture'}<={s['origin'] for s in c.sources}:raise ValueError('mixed source lacks component lineage')
        if routes:
            pairs=[(e['from'],e['to']) for e in routes['edges']]
            if len(pairs)!=len(set(pairs)):raise ValueError('duplicate directed route')
            if c.case_id=='R10':required={(a,b) for p in ref['permutations'] for a,b in zip(p['sequence'],p['sequence'][1:])}
            else:required=set(itertools.permutations(routes['nodes'],2))
            if required-set(pairs):raise ValueError('missing directed route; no live fallback allowed')
            for e in routes['edges']:
                if e['duration_minutes']<=0 or e['duration_seconds']<=0 or e['is_estimated']:raise ValueError('invalid/estimated frozen route')
                if c.case_id=='R10' and e['source']!='amap_mcp_live_20261024':raise ValueError('mixed route origin changed')
                if c.case_id!='R10' and e['source']!='synthetic':raise ValueError('artificial route mislabelled real')
            route_audit[c.case_id]={'required':len(required),'available':len(pairs),'missing':0}
        if c.case_id=='T18' and (len(inp['candidates'])!=80 or len(ref['eligible_ids'])!=35 or ref['acceptable_first'] is not None):raise ValueError('T18 source/annotation contract changed')
        if c.case_id=='R10' and (len(routes['edges'])!=23 or len(ref['permutations'])!=20 or ref['baseline_traffic_minutes']!=180):raise ValueError('R10 source/route contract changed')
    return dict(status='PASS_INPUT_INTEGRITY',cases=len(cases),targets=dict(Counter(c.target for c in cases)),splits=dict(splits),modes=dict(modes),
        origins=dict(Counter(c.data_origin for c in cases)),rules=len(RULES),route_coverage=route_audit,
        pending_human=sum(c.annotation.status!='confirmed' for c in cases),formal_ready=all(c.annotation.status=='confirmed' for c in cases) and manifest['split_review']=='confirmed',
        cross_split_source_families=sorted(k for k,v in families.items() if len(v)>1),
        split_review=manifest['split_review'],external_calls=0,business_database_used=False,uploaded_to_langsmith=False)


def review_queue(root=DATA):
    return [dict(case_id=c.case_id,title=c.title,split=c.split,data_origin=c.data_origin,reference_sha256=c.reference_sha256,
        reference_path=c.reference_path,status=c.annotation.status,pending_items=c.annotation.pending_items,
        reviewer=c.annotation.reviewer,reviewed_at=c.annotation.reviewed_at,
        priority='high' if c.case_id in {'T18','R10'} else 'normal') for c,*_ in load_all(root)]
