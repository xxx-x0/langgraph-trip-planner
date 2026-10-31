"""Local commands only. No inference, business DB access, SDK export or network."""
import argparse
import json
from pathlib import Path
from .dataset import load_all, load_case, read_json
from .scorers import evaluate
from .reporting import summarize
from .validation import validate, review_queue


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command',choices=['validate','review','selftest','score'])
    parser.add_argument('--input',type=Path,help='captured observation JSON for score')
    parser.add_argument('--allow-provisional',action='store_true',help='diagnostics only, never human confirmation')
    parser.add_argument('--output',type=Path)
    args=parser.parse_args()
    if args.command=='validate':result=validate()
    elif args.command=='review':result={'status':'PENDING_HUMAN','cases':review_queue()}
    elif args.command=='score':
        if not args.input:parser.error('score requires --input')
        observation=read_json(args.input)
        result=evaluate(*load_case(observation['case_id']),observation,allow_provisional=args.allow_provisional)
    else:
        from .selftest import observation_vector
        reports=[]
        for case,*_ in load_all():
            bundle,obs=observation_vector(case.case_id)
            reports.append(evaluate(*bundle,obs,allow_provisional=True))
        unexpected=[]
        for report in reports:
            bad={(c['rule_id'],c['layer'],c['status']) for c in report['checks'] if c['status'] in {'ERROR','FAIL'}}
            expected={('T-VALID','model','FAIL')} if report['case_id']=='T13' else set()
            if bad!=expected:unexpected.append(report['case_id'])
        result={'kind':'SCORER_SELFTEST_ONLY','status':'FAIL' if unexpected else 'PASS_KNOWN_VECTORS','unexpected_cases':unexpected,
            'not_business_experiment':True,'live_model_calls':0,
            'observations':'fabricated known-output vectors, including intentionally invalid model selections',
            'summary':summarize(reports),'reports':reports}
    text=json.dumps(result,ensure_ascii=False,indent=2,allow_nan=False)+'\n'
    if args.output:
        args.output.parent.mkdir(parents=True,exist_ok=True)
        args.output.write_text(text,encoding='utf-8')
        print(f'{args.command}: wrote local report to {args.output}')
    else:print(text)
    if args.command=='selftest' and result['unexpected_cases']:raise SystemExit(1)


if __name__=='__main__':main()
