"""Counts retain missing/error/unreviewed results; injected models stay separate."""
from collections import Counter, defaultdict


def counts(checks):
    n=Counter(c['status'] for c in checks)
    p,f,e,u,na=(n[k] for k in ['PASS','FAIL','ERROR','NOT_EVALUATED','NOT_APPLICABLE'])
    scored=p+f;applicable=scored+e+u
    return dict(P=p,F=f,E=e,U=u,NA=na,scored_pass_rate=p/scored if scored else None,
        coverage=scored/applicable if applicable else None,acceptance_completion=p/applicable if applicable else None)


def summarize(reports):
    groups=defaultdict(list);seen=set()
    for report in reports:
        identity=(report['case_id'],report['run_id'])
        if identity in seen:raise ValueError('duplicate case/run must not count twice')
        seen.add(identity)
        for check in report['checks']:
            key=tuple(report[k] for k in ['target','split','data_origin','execution_mode','provenance'])+(check['rule_id'],check['layer'])
            groups[key].append(check)
    labels=['target','split','data_origin','execution_mode','provenance','rule_id','layer']
    return dict(unique_cases=len({r['case_id'] for r in reports}),runs=len(reports),
        pending_reference_cases=len({r['case_id'] for r in reports if r['reference_status']!='confirmed'}),
        formal_acceptances=sum(r['formal_acceptance'] for r in reports),
        live_model_quality_runs=sum(r['model_quality_included'] for r in reports),
        groups=[dict(zip(labels,key),**counts(values)) for key,values in sorted(groups.items())])
