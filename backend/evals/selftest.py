"""Fabricated observation vectors for scorer testing, NEVER experimental results.

References may be used here to construct known expected evidence; a real runner
must capture business outputs independently. Every vector is scorer_selftest.
"""
import copy
from .contracts import Observation
from .build_dataset import leg, reference_timeline
from .dataset import load_case


def trace_vector(cid,status,calls,outcome):
    root=dict(id='selftest-'+cid,parent_id=None,name='ticket_recommendation' if cid.startswith('T') else 'day_rearrangement',run_type='chain',
        start_time='2027-01-01T00:00:00+00:00',end_time='2027-01-01T00:00:01+00:00',dotted_order='root-'+cid,status=status,facts={})
    stages=['snapshot_read','eligibility'] if cid.startswith('T') else ['snapshot_read','model_suggestion']
    if status=='success':
        if cid.startswith('T'):
            if not outcome.startswith('empty_'):stages+=['model_selection','output_validation']
            if outcome=='fallback':stages+=['rule_fallback']
        else:
            stages+=['output_validation','constraint_repair','route_calculation','schedule_validation','fact_projection','cas_save']
            if outcome=='preserved_original':stages+=['saved_schedule_recovery']
    children=[dict(id=f'call-{cid}-{n}',parent_id=root['id'],name='model_call',run_type='llm',start_time=root['start_time'],end_time=root['end_time'],
        dotted_order=root['dotted_order']+f'.{n}',status='success',facts={'usage_known':True,'input_tokens':10,'output_tokens':5,'total_tokens':15}) for n in range(calls)]
    children += [dict(id=f'stage-{cid}-{n}',parent_id=root['id'],name=name,run_type='chain',start_time=root['start_time'],end_time=root['end_time'],dotted_order=root['dotted_order']+f'.s{n}',status='success',facts={}) for n,name in enumerate(stages)]
    return dict(operation_id=root['id'],spans=[root]+children)


def proposal(day):
    rows=[];anchor='hotel_start'
    by_name={m['name']:m for m in day['meals']}
    for step in day['timeline_order']:
        if step['kind']=='attraction':anchor=step['ref_name']
        elif step['kind']=='meal':rows.append(dict(by_name[step['ref_name']],insert_after=anchor))
    return {'attractions_order':[a['name'] for a in day['attractions']],'meals':rows}


def known_day(inp,ref,routes):
    d=copy.deepcopy(inp['day_detail']);attrs={a['name']:a for a in d['attractions']};meal_by={m['name']:m for m in d['meals']}
    if ref.get('required_route_improvement'):
        p=min((p for p in ref['permutations'] if p['feasible']),key=lambda p:p['traffic_minutes'])
        seq=p['sequence'];d['attractions']=[attrs[n] for n in seq if n in attrs]
        d['timeline_order']=[dict(kind='attraction' if n in attrs else 'meal' if n in meal_by else 'hotel',ref_name=n,**({'phase':'start' if j==0 else 'end'} if n not in attrs and n not in meal_by else {})) for j,n in enumerate(seq)]
        d['timeline_schedule']=[dict(kind=t['kind'],ref_name=t['from']+' → '+t['to'] if t['kind']=='travel' else t.get('name',d['hotel']['name']),start_minutes=t['start'],end_minutes=t['end'],duration=t['duration']) for t in p['timeline']]
    else:
        if ref['expected_order']:d['attractions']=[attrs[n] for n in ref['expected_order']]
        order=[a['name'] for a in d['attractions']]
        meal_after={}
        anchor=None
        for t in inp['day_detail']['timeline_order']:
            if t['kind']=='attraction':anchor=t['ref_name']
            if t['kind']=='meal':meal_after[t['ref_name']]=anchor
        steps=[]
        if d['hotel']:steps.append(dict(kind='hotel',ref_name=d['hotel']['name'],phase='start'))
        for index,name in enumerate(order):
            steps.append(dict(kind='attraction',ref_name=name))
            for m in d['meals']:
                desired=meal_after[m['name']] if m.get('schedule_mode')=='manual' else order[0] if m['type']=='lunch' else order[-1]
                if desired==name:steps.append(dict(kind='meal',ref_name=m['name']))
        if d['hotel']:steps.append(dict(kind='hotel',ref_name=d['hotel']['name'],phase='end'))
        d['timeline_order']=steps
        d['timeline_schedule']=reference_timeline(d,routes['edges'],ref['hard_constraints'])
    matrix={(e['from'],e['to']):e for e in routes['edges']};seq=[s['ref_name'] for s in d['timeline_order']]
    d['route_segments']=[]
    for a,b in zip(seq,seq[1:]):
        e=matrix[a,b];d['route_segments'].append(dict(from_name=a,to_name=b,mode=e['mode'],duration=f"{e['duration_minutes']}分钟",is_estimated=False))
    d['description']='自检人工输出：'+ '、'.join(a['name'] for a in d['attractions'])
    return d


def observation_vector(cid,root=None):
    bundle=load_case(cid,**({'root':root} if root else {}));case,inp,ref,routes=bundle
    expected=ref['expected_outcome'];status=expected if expected in {'cancelled','conflict','timeout','rejected'} else 'success'
    calls=1 if case.execution_mode=='live_model_with_replay' else 0
    base=dict(case_id=cid,case_version=case.case_version,input_sha256=case.input_sha256,run_id='selftest-'+cid,
        execution_status=status,http_status=ref['expected_http'],business_outcome=expected,model_status='success',provenance='scorer_selftest',
        actual_model_calls=calls,external_calls_after_cancel=0,recovery_count=1 if cid in {'R07','R08'} else 0,route_deadline_seconds=110 if cid=='R11' else None,
        checkpoint_statuses=ref.get('checkpoint_statuses'),trace=trace_vector(cid,status,calls,expected))
    if case.target=='ticket_recommendation':
        source={c['id']:c for c in inp['candidates']};ids=ref['eligible_ids'];first=(ref['acceptable_first'] or ids or [None])[0]
        selected=([first]+[i for i in ids if i!=first])[:3] if ids else []
        if ref.get('rank_key')=='price':selected=sorted(selected,key=lambda i:source[i]['fare_per_person'] if source[i]['fare_per_person'] is not None else float('inf'))
        raw={'ids':selected}
        if cid=='T13':raw=inp['fault']['response']
        if cid in {'T07','T14','T15','T16'}:raw=None;base['model_status']='not_called' if cid in {'T07','T14'} else 'timeout' if cid=='T15' else 'cancelled'
        recommendations=[];checks={c['candidate_id']:c for c in ref['candidate_checks']}
        for id in selected:
            c=source[id];reasons=['同行总价未知；列表每人参考价不计入预算']
            if c['fare_per_person'] is None:reasons.append('价格未知')
            if c['availability']=='unknown':reasons.append('余票未知')
            if checks[id]['tight']:reasons.append('时间较紧')
            if not inp['context']:reasons.append('未核对已存安排')
            l=leg(c,ref['buffer_fields']);l.update(service_number=c['service'],seat_class=c['seat'],price_note='未确认为同行总价',passengers=inp['query']['passengers'])
            recommendations.append(dict(candidate=copy.deepcopy(c),leg=l,reasons=reasons))
        output=dict(recommendations=recommendations,ranked_by='rules' if expected=='fallback' or not ids else 'ai',checked_schedule=bool(inp['context']),
            schedule_basis='selftest-basis' if inp['context'] else None,message='规则回退' if expected=='fallback' else '当前无票或候补' if expected=='empty_unavailable' else '当前读取候选都冲突' if expected=='empty_conflict' else '未核对已有安排' if not inp['context'] else '按保存安排核对')
        before=copy.deepcopy(inp['saved_state']);after=copy.deepcopy(before);latest=None
        if cid=='T17':latest=copy.deepcopy(before);latest['plan']['budget']=9999;latest['revision']+=1;after=copy.deepcopy(latest)
        base.update(raw_model=raw,final_output=output if status=='success' else None,eligible_ids=ids,candidate_checks=copy.deepcopy(ref['candidate_checks']),before_state=before,after_state=after,latest_state=latest)
    else:
        before={'request':copy.deepcopy(inp['request']),'days_detail':[copy.deepcopy(inp['day_detail'])]};after=copy.deepcopy(before);latest=None
        d=known_day(inp,ref,routes);raw=proposal(d)
        if cid in {'R07','R08'}:raw=copy.deepcopy(inp['fault']['response'])
        if cid=='R07':
            d=copy.deepcopy(inp['day_detail']);d['meal_adjustments']=['AI建议与营业时段冲突，已保留原安排。'];d['description']='已保留原安排'
        if cid=='R12':
            latest=copy.deepcopy(before);day=latest['days_detail'][0]
            removed={m['name'] for m in day['meals'] if m['type']=='dinner'};day['meals']=[m for m in day['meals'] if m['type']!='dinner']
            day['timeline_order']=[x for x in day['timeline_order'] if x['ref_name'] not in removed]
            day['description']='并发新状态已删除晚餐';after=copy.deepcopy(latest)
        if status=='success':after['days_detail'][0]=copy.deepcopy(d)
        base.update(raw_model=raw,final_output=d if status=='success' else None,before_state=before,after_state=after,latest_state=latest)
    return bundle,Observation.model_validate(base)
