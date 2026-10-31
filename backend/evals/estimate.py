"""Quote only: captured production prompts, no model request and no API key reads."""
import argparse
from pathlib import Path
from .budget import RATES,prompt_bound,estimated_cost
from .contracts import digest
from .dataset import read_json,load_case
from .experiment import verified_plan,atomic,sha


def estimate(directory,*,repeats=3):
    if repeats not in {1,2,3}:raise ValueError('repeats must be 1..3')
    directory=Path(directory).resolve();plan=verified_plan(directory);ledger=read_json(directory/'ledger.json')
    rows=[];case_ids=[]
    for slot in plan['slots']:
        if slot['variant']!='current_replay' or slot['repetition']!=1:continue
        cid=slot['case_id'];case_ids.append(cid);c,*_=load_case(cid,directory/'source/evals/datasets')
        if c.execution_mode!='live_model_with_replay':continue
        entry=ledger['slots'].get(slot['slot_id'],{});work=directory/'slots'/slot['slot_id']
        if entry.get('state')!='COMPLETED' or sha(work/'engineering.json')!=entry.get('engineering_sha256'):raise ValueError('need completed intact replay prompt capture for '+cid)
        e=read_json(work/'engineering.json');prompts=e['captured_prompts']
        if len(prompts)!=1:raise ValueError('one frozen production prompt required for '+cid)
        inp=prompt_bound(prompts[0]);attempts=1 if cid.startswith('T') else 2
        output_typical=256 if cid.startswith('T') else 1024
        rows.append(dict(case_id=cid,repetitions=repeats,max_attempts_per_run=attempts,max_requests=repeats*attempts,
            prompt_sha256=digest(prompts[0]),input_token_reservation_per_request=inp,max_output_tokens=8192,
            max_tokens_per_run=attempts*(inp+8192),max_cost_per_run=estimated_cost(inp*attempts,8192*attempts),
            expected_input_tokens_low=max(1,inp//4),expected_input_tokens_high=inp,assumed_output_tokens=output_typical))
    if not rows:raise ValueError('no captured live-model scenarios')
    requests=sum(r['max_requests'] for r in rows);nominal=sum(r['repetitions'] for r in rows)
    input_low=sum(r['expected_input_tokens_low']*repeats for r in rows);input_high=sum(r['expected_input_tokens_high']*repeats for r in rows)
    assumed_output=sum(r['assumed_output_tokens']*repeats for r in rows)
    upper_input=sum(r['input_token_reservation_per_request']*r['max_requests'] for r in rows);upper_output=requests*8192
    result=dict(schema='trip-usage-estimate-v1',source_sha256=plan['source_sha256'],dataset_sha256=plan['dataset_sha256'],
        model=plan['model'],rates=RATES,case_ids=case_ids,repeats=repeats,rows=rows,
        nominal_live_requests=nominal,max_live_requests=requests,planned_current_slots=sum(repeats if c in {r['case_id'] for r in rows} else 1 for c in case_ids),
        expected_tokens=dict(input_low=input_low,input_high=input_high,assumed_output=assumed_output),
        expected_cost_peak_usd_range=[estimated_cost(input_low,assumed_output),estimated_cost(input_high,assumed_output)],
        reservation=dict(max_model_requests=requests,max_total_tokens=upper_input+upper_output,max_cost=estimated_cost(upper_input,upper_output),currency='USD'),
        calls_made=0,approved=False,
        assumptions=['Input interval is a UTF-8 byte heuristic, not measured tokens','Expected output is a planning assumption, not observed model output','Reservation includes full 8192 output tokens per attempt and up to two daily attempts','Direct DeepSeek peak cache-miss rates; no cache/off-peak savings assumed','Judge and cloud export disabled','Unknown billed usage stops continuation; reservations are not refunded automatically'])
    result['estimate_sha256']=digest(result);return result


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--directory',type=Path,required=True);p.add_argument('--repeats',type=int,default=3);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    result=estimate(a.directory,repeats=a.repeats);atomic(a.output,result)
    print('Estimate only; no model calls. '+result['estimate_sha256'])


if __name__=='__main__':main()
