"""Deterministic, evidence-based scoring. No production scheduling/filter imports.

References are frozen proposals; strict mode abstains on reference-dependent rules
until human confirmation. Diagnostic mode marks those results provisional.
"""
from collections import Counter
from datetime import datetime
import math
import re

from .contracts import Check, Observation, JudgeCalibration, HARD_RULES, REFERENCE_RULES, digest


class MissingEvidence(Exception):pass
class PendingReference(Exception):pass


def need(value):
    if value is None:raise MissingEvidence()
    return value


def same(a,b):return digest(a)==digest(b)
def names(day):return [a['name'] for a in day['attractions']]
def selected(obs,layer):
    if layer=='model':return need(obs.raw_model)['ids']
    return [r['candidate']['id'] for r in need(obs.final_output)['recommendations']]


def output_day(obs):return need(obs.final_output)


def order(obs,layer):
    if layer=='model':return need(obs.raw_model).get('attractions_order',[])
    return names(output_day(obs))


def meal_slot(m,original):
    if m.get('type') in {'breakfast','lunch','dinner'}:return m['type']
    if m.get('preferred_slot') in {'breakfast','lunch','dinner'}:return m['preferred_slot']
    return next((x['type'] for x in original if x['name']==m.get('name')),m.get('type',m.get('category','unknown')))


def meals(obs,layer):
    if layer=='model':return need(obs.raw_model).get('meals',[])
    return output_day(obs)['meals']


def meal_counts(rows,original):
    return Counter(meal_slot(m,original) for m in rows)


def previous_attraction(day,meal_name):
    anchor=None
    for entry in day['timeline_order']:
        if entry['kind']=='attraction':anchor=entry['ref_name']
        if entry['kind']=='meal' and entry['ref_name']==meal_name:return anchor
    raise MissingEvidence()


def clock_minutes(text):return int(text[:2])*60+int(text[3:5])


def duration_minutes(segment):
    value=segment.get('duration','')
    match=re.fullmatch(r'(\d+)分钟',value)
    if not match:raise MissingEvidence()
    return int(match[1])


def route_facts(day,routes):
    """Directed lookup only, no estimate/reverse-edge/live-provider fallbacks."""
    matrix={(e['from'],e['to']):e for e in need(routes)['edges']}
    sequence=[s['ref_name'] for s in day['timeline_order'] if s['kind'] in {'hotel','attraction','meal'}]
    expected=list(zip(sequence,sequence[1:]));actual=[(s['from_name'],s['to_name']) for s in day['route_segments']]
    violations=[];total=0
    if actual!=expected:violations.append('route_sequence_mismatch')
    for seg in day['route_segments']:
        key=(seg['from_name'],seg['to_name'])
        if key not in matrix:raise MissingEvidence()
        e=matrix[key];total+=e['duration_minutes']
        if seg.get('is_estimated') is not False:violations.append('estimated_route')
        if duration_minutes(seg)!=e['duration_minutes'] or seg['mode']!=e['mode']:violations.append('route_fact_changed')
    return total,violations


def window_violations(day,hard,routes):
    rows=need(day.get('timeline_schedule'))
    if not rows:raise MissingEvidence()
    violations=[];last=None
    for row in rows:
        start,end=row['start_minutes'],row['end_minutes']
        if not isinstance(start,(int,float)) or not isinstance(end,(int,float)) or not math.isfinite(start+end):raise MissingEvidence()
        if end<start or (last is not None and start<last):violations.append('overlap_or_negative_duration')
        last=end
        if start<hard['start_minutes'] or end>hard['end_latest']:violations.append('outside_day_window')
        if row.get('duration')!=end-start:violations.append('duration_field_mismatch')
        kind,name=row['kind'],row['ref_name']
        if kind not in {'travel','attraction','meal','hotel','rest','free_time','wait'}:violations.append('unknown_timeline_kind')
        if kind in {'attraction','meal'}:
            windows=hard['opening_windows'].get(name)
            if windows is None:raise MissingEvidence()
            if not any(lo<=start and end<=hi for lo,hi in windows):violations.append('closed_place')
            deadline=hard.get('last_entry_deadlines',{}).get(name)
            if deadline is not None and start>deadline:violations.append('after_last_entry')
        if kind=='attraction':
            attr=next((a for a in day['attractions'] if a['name']==name),None)
            if not attr or end-start!=attr['visit_duration']:violations.append('attraction_duration_changed')
        if kind=='meal':
            m=next((m for m in day['meals'] if m['name']==name),None)
            if not m:violations.append('unknown_meal');continue
            slot=meal_slot(m,day['meals'])
            if slot in {'lunch','dinner'}:
                lo,hi=hard[slot+'_start_range']
                if not lo<=start<=hi or end-start!=60:violations.append('meal_window')
    expected=Counter((x['kind'],x['ref_name']) for x in day['timeline_order'] if x['kind'] in {'attraction','meal'})
    actual=Counter((x['kind'],x['ref_name']) for x in rows if x['kind'] in {'attraction','meal'})
    if expected!=actual:violations.append('missing_or_extra_scheduled_activity')
    scheduled_order=[(x['kind'],x['ref_name']) for x in rows if x['kind'] in {'attraction','meal'}]
    declared_order=[(x['kind'],x['ref_name']) for x in day['timeline_order'] if x['kind'] in {'attraction','meal'}]
    if scheduled_order!=declared_order:violations.append('timeline_order_changed')
    if [x['ref_name'] for x in day['timeline_order'] if x['kind']=='attraction']!=names(day):violations.append('attraction_order_mismatch')
    expected_hotels=[x['ref_name'] for x in day['timeline_order'] if x['kind']=='hotel' and x.get('phase')=='end']
    actual_hotels=[x['ref_name'] for x in rows if x['kind']=='hotel']
    if actual_hotels!=expected_hotels:violations.append('missing_hotel_task')
    if any(x['end_minutes']-x['start_minutes']!=30 for x in rows if x['kind']=='hotel'):violations.append('hotel_duration_changed')
    _,route_errors=route_facts(day,routes);violations+=route_errors
    travels=[x for x in rows if x['kind']=='travel']
    segs=day['route_segments']
    if len(travels)!=len(segs):violations.append('missing_travel_time')
    else:
        for row,seg in zip(travels,segs):
            if row['ref_name']!=seg['from_name']+' → '+seg['to_name'] or row['end_minutes']-row['start_minutes']!=duration_minutes(seg):violations.append('travel_time_changed')
    return sorted(set(violations))


def rest_violations(before,after):
    errors=[];rests=before.get('rest_periods',[])
    if not same(rests,after.get('rest_periods',[])):errors.append('rest_definition_changed')
    rows=need(after.get('timeline_schedule'))
    for rest in rests:
        lo,hi=clock_minutes(rest['start_time']),clock_minutes(rest['end_time'])
        matches=[r for r in rows if r['kind']=='rest' and (r['ref_name']==rest['id'] or r.get('rest_id')==rest['id'])]
        if len(matches)!=1 or matches[0]['start_minutes']!=lo or matches[0]['end_minutes']!=hi:errors.append('missing_or_moved_rest')
        if any(r['kind'] not in {'rest','free_time'} and r['start_minutes']<hi and r['end_minutes']>lo for r in rows):errors.append('activity_overlaps_rest')
    return errors


def day_constraints(rule,layer,inp,ref,obs,routes):
    if rule=='R-INTENT' and obs.execution_status!='success':
        return False,'requested adjustment completes',obs.execution_status,['execution_status']
    before=inp['day_detail'];after=output_day(obs) if layer=='system' else None
    got=order(obs,layer)
    if rule=='R-LOCK':
        bad=[n for n in before['locked_attraction_names'] if n not in got or got.index(n)!=names(before).index(n)]
        return not bad,{'locked':before['locked_attraction_names']},{'violations':bad},['raw_model.attractions_order' if layer=='model' else 'final_output.attractions']
    if rule=='R-REMOVED':
        removed=set(before['removed_attraction_names']);rows=meals(obs,layer)
        anchors=[m.get('insert_after') for m in rows] if layer=='model' else [x['ref_name'] for x in after['timeline_order']]
        ok=Counter(got)==Counter(names(before)) and not (removed & (set(got)|set(anchors)))
        if layer=='system':ok=ok and Counter(after['removed_attraction_names'])==Counter(before['removed_attraction_names'])
        # Missing meal slots express current intent even when candidate pools retain them.
        ok=ok and not (set(meal_counts(rows,before['meals']))-set(meal_counts(before['meals'],before['meals'])))
        return ok,{'retained':names(before),'removed':sorted(removed)},got,['raw_model' if layer=='model' else 'final_output']
    if rule=='R-MEAL':
        expected=meal_counts(before['meals'],before['meals']);actual=meal_counts(meals(obs,layer),before['meals'])
        return expected==actual,dict(expected),dict(actual),['raw_model.meals' if layer=='model' else 'final_output.meals']
    if rule=='R-MANUAL':
        bad=[]
        for m in before['meals']:
            if m.get('schedule_mode')!='manual':continue
            kept=[v for v in after['meals'] if v['name']==m['name']]
            if len(kept)!=1 or meal_slot(kept[0],before['meals'])!=meal_slot(m,before['meals']) or kept[0].get('schedule_mode')!='manual' or previous_attraction(before,m['name'])!=previous_attraction(after,m['name']):bad.append(m['name'])
        return not bad,'manual restaurant, slot and anchor unchanged',bad,['final_output.meals','final_output.timeline_order']
    if rule=='R-FACT':
        sources={m['name']:m for m in inp['dining_candidates']};sources.update({m['name']:m for m in before['meals']})
        bad=[]
        for m in after['meals']:
            source=sources.get(m['name'])
            if source is None:bad.append('unknown_restaurant');continue
            for key in ['address','location','poi_id','avg_cost','estimated_cost','source','open_hours','cuisine','rating']:
                expected=source.get(key,source.get('avg_cost',0) if key=='estimated_cost' else None)
                if m.get(key)!=expected:bad.append(key)
        source_attrs={a['name']:a for a in before['attractions']}
        for a in after['attractions']:
            if a['name'] not in source_attrs:bad.append('unknown_attraction');continue
            if any(a.get(k)!=source_attrs[a['name']].get(k) for k in ['location','address','ticket_price','open_hours']):bad.append('attraction_fact_changed')
        return not bad,'facts from current meal or candidate',sorted(set(bad)),['final_output.meals']
    if rule=='R-DURATION':
        expected={a['name']:a['visit_duration'] for a in before['attractions']};actual={a['name']:a['visit_duration'] for a in after['attractions']}
        return expected==actual and len(actual)==len(after['attractions']),expected,actual,['final_output.attractions']
    if rule=='R-REST':
        errors=rest_violations(before,after)
        return not errors,'fixed rests remain occupied at the same intervals',errors,['final_output.rest_periods','final_output.timeline_schedule']
    if rule=='R-WINDOW':
        errors=window_violations(after,ref['hard_constraints'],routes)
        return not errors,'known openings, meals, route timing and day window valid',errors,['final_output.timeline_schedule','final_output.route_segments']
    if rule=='R-ROUTE':
        total,errors=route_facts(after,routes)
        errors+=window_violations(after,ref['hard_constraints'],routes)+rest_violations(before,after)
        for r in ['R-LOCK','R-REMOVED','R-MEAL','R-MANUAL','R-FACT','R-DURATION']:
            if not day_constraints(r,'system',inp,ref,obs,routes)[0]:errors.append(r)
        return not errors and total<ref['baseline_traffic_minutes'],{'baseline_minutes':ref['baseline_traffic_minutes'],'must_improve':True},{'final_minutes':total,'delta_minutes':ref['baseline_traffic_minutes']-total,'violations':sorted(set(errors))},['final_output.route_segments','final_output.timeline_schedule']
    if rule=='R-INTENT':
        if ref['intent_kind']=='route_improvement':
            if layer=='model':
                raw=need(obs.raw_model);suggested=raw.get('meals',[])
                if any('insert_after' not in m for m in suggested):raise MissingEvidence()
                hotel=before['hotel']['name'];sequence=[hotel]
                for anchor in ['hotel_start']+got+['hotel_end']:
                    if anchor not in {'hotel_start','hotel_end'}:sequence.append(anchor)
                    sequence.extend(m['name'] for m in suggested if m['insert_after']==anchor)
                sequence.append(hotel)
                matches=[p for p in ref['permutations'] if p['sequence']==sequence]
                ok=bool(matches) and matches[0]['feasible'] and matches[0]['traffic_minutes']<ref['baseline_traffic_minutes']
                return ok,'known feasible improvement under frozen matrix',{'matched_permutation':matches[0]['permutation_id'] if matches else None},['raw_model.attractions_order','raw_model.meals']
            return day_constraints('R-ROUTE','system',inp,ref,obs,routes)
        expected=ref['expected_order'];ok=got==expected if expected is not None else Counter(got)==Counter(names(before))
        for r in ['R-LOCK','R-REMOVED','R-MEAL']:
            ok=ok and day_constraints(r,layer,inp,ref,obs,routes)[0]
        if layer=='system':
            ok=ok and not window_violations(after,ref['hard_constraints'],routes) and not rest_violations(before,after)
            ok=ok and day_constraints('R-MANUAL','system',inp,ref,obs,routes)[0] and day_constraints('R-FACT','system',inp,ref,obs,routes)[0]
        return ok,expected or 'preserve explicit constraints (no optimality claim)',got,['raw_model' if layer=='model' else 'final_output']
    if rule=='R-DISCLOSE':
        raw=need(obs.raw_model);raw_order=raw.get('attractions_order',[])
        changed=raw_order!=names(after) or Counter(m.get('name') for m in raw.get('meals',[]))!=Counter(m['name'] for m in after['meals'])
        notes=after.get('meal_adjustments',[]);text=' '.join(notes)+after.get('description','')
        preserved=obs.business_outcome=='preserved_original'
        disclosed=bool(notes) and any(word in ' '.join(notes) for word in ['保留','修正','调整','锁定'])
        ok=(not changed or disclosed) and (not preserved or ('保留' in text and not any(x in text for x in ['完全按要求','已按要求调整'])))
        return ok,{'correction_disclosed':changed,'preserved_original':preserved},{'has_adjustment':bool(notes)},['raw_model','final_output.meal_adjustments','final_output.description']
    raise ValueError('unknown day rule')


def ticket_rule(rule,layer,inp,ref,obs):
    source={c['id']:c for c in inp['candidates']};result=obs.final_output
    if rule=='T-VALID':
        if layer=='model' and obs.raw_model is None and obs.model_status in {'error','timeout'}:
            return False,'valid completed model selection',obs.model_status,['model_status']
        ids=selected(obs,layer);allowed=set(need(obs.eligible_ids))
        ok=1<=len(ids)<=3 and len(set(ids))==len(ids) and set(ids)<=allowed and set(ids)<=source.keys()
        return ok,{'count':[1,3],'eligible_count':len(allowed)},ids,['raw_model.ids' if layer=='model' else 'final_output.recommendations','eligible_ids']
    if rule=='T-ELIG':
        actual=need(obs.eligible_ids);expected=ref['eligible_ids'];a=set(actual);e=set(expected)
        return a==e and len(a)==len(actual),expected,dict(eligible_ids=actual,false_accepts=sorted(a-e),false_rejects=sorted(e-a),precision=len(a&e)/len(a) if a else None,recall=len(a&e)/len(e) if e else None),['eligible_ids']
    if rule=='T-FACT':
        bad=[]
        for rec in need(result)['recommendations']:
            candidate=rec['candidate'];s=source.get(candidate['id'])
            if s is None:bad.append('unknown_candidate');continue
            if any(candidate.get(k)!=v for k,v in s.items()):bad.append('candidate_fact_changed')
            leg=rec['leg']
            for key,ck in [('departure_time','departure'),('arrival_time','arrival'),('departure_station','from_station'),('arrival_station','to_station'),('mode','mode'),('service_number','service'),('seat_class','seat')]:
                if leg.get(key)!=s.get(ck):bad.append(key)
            if leg.get('ticket_total','missing') is not None or leg.get('price_source')!='unknown' or leg.get('passengers')!=inp['query']['passengers']:bad.append('unverified_party_price')
            if inp['context']:
                for k,v in ref['buffer_fields'].items():
                    if leg.get(k)!=v:bad.append(k)
        return not bad,'source facts and saved buffers unchanged; party total unknown',sorted(set(bad)),['final_output.recommendations']
    if rule=='T-MARGIN':
        actual=need(obs.candidate_checks);expected={c['candidate_id']:c for c in ref['candidate_checks']};bad=[]
        if len(actual)!=len(expected) or {c['candidate_id'] for c in actual}!=expected.keys():bad.append('incomplete_candidate_checks')
        for c in actual:
            need(c.get('margins'))
            e=expected.get(c['candidate_id'])
            if e is None or c.get('margins')!=e['margins'] or c.get('tight')!=e['tight']:bad.append(c['candidate_id'])
        return not bad,'all candidate interval margins and <=30 minute flags',bad,['candidate_checks']
    if rule=='T-RANK':
        acceptable=ref['acceptable_first']
        if acceptable is None:raise PendingReference()
        ids=selected(obs,layer)
        ok=bool(ids) and ids[0] in acceptable and all(i in source and i in ref['eligible_ids'] for i in ids)
        if not ok:return False,acceptable,ids,['raw_model.ids' if layer=='model' else 'final_output.recommendations']
        key=ref.get('rank_key')
        if key:
            values=[(source[i]['fare_per_person'] if source[i]['fare_per_person'] is not None else math.inf) if key=='price' else (datetime.fromisoformat(source[i]['arrival'])-datetime.fromisoformat(source[i]['departure'])).total_seconds() for i in ids]
            ok=values==sorted(values)
        for a,b in ref.get('preferred_pairs',[]):
            if a in ids and b in ids and ids.index(a)>ids.index(b):ok=False
        return ok,acceptable,ids,['raw_model.ids' if layer=='model' else 'final_output.recommendations']
    if rule=='T-DISCLOSE':
        if obs.execution_status!='success':
            return True,'failure has no recommendation claim',obs.execution_status,['execution_status']
        r=need(result);bad=[]
        if r.get('checked_schedule')!=bool(inp['context']):bad.append('schedule_check_claim')
        if not inp['context'] and (r.get('schedule_basis') is not None or '未核对' not in r.get('message','')+' '.join(' '.join(x['reasons']) for x in r['recommendations'])):bad.append('unverified_schedule_not_disclosed')
        if r.get('ranked_by')=='rules' and r['recommendations'] and not any(w in r.get('message','') for w in ['规则','回退']):bad.append('fallback_not_disclosed')
        checks={x['candidate_id']:x for x in ref['candidate_checks']}
        for rec in r['recommendations']:
            c=rec['candidate'];text=' '.join(rec['reasons'])+' '+rec['leg'].get('price_note','')
            if c.get('fare_per_person') is None and not any(w in text for w in ['价格未读取','价格未知','未知价']):bad.append('unknown_fare_not_disclosed')
            if c.get('availability')=='unknown' and not any(w in text for w in ['余票尚未确认','余票未知']):bad.append('unknown_availability_not_disclosed')
            if not any(w in text for w in ['未确认为同行总价','同行总额待核对','同行总价未知']):bad.append('party_price_not_disclosed')
            if checks[c['id']]['tight'] and '紧张' not in text and '较紧' not in text:bad.append('tight_margin_not_disclosed')
        return not bad,'applicable unknown/fallback/tight/schedule limitations disclosed',bad,['final_output']
    if rule=='T-OUTCOME':
        expected=ref['expected_outcome'];actual=need(obs.business_outcome);ok=actual==expected
        if ref['expected_http'] is not None:ok=ok and obs.http_status==ref['expected_http']
        if not ok:return False,expected,actual,['execution_status','business_outcome','http_status']
        if expected in {'recommended','fallback','empty_unavailable','empty_conflict'}:
            r=need(result);ok=ok and obs.execution_status=='success'
            ok=ok and bool(r['recommendations'])==(expected in {'recommended','fallback'})
            if expected=='fallback':ok=ok and r['ranked_by']=='rules'
            if expected.startswith('empty_'):
                ok=ok and need(obs.actual_model_calls)==0
                text=r.get('message','')
                ok=ok and ('冲突' in text if expected=='empty_conflict' else ('无票' in text or '候补' in text) and '日程冲突' not in text)
        if expected=='cancelled':ok=ok and obs.execution_status=='cancelled' and obs.final_output is None and need(obs.external_calls_after_cancel)==0
        if expected=='conflict':ok=ok and obs.execution_status=='conflict' and need(obs.checkpoint_statuses)==ref['checkpoint_statuses']
        return ok,expected,actual,['execution_status','business_outcome','http_status','checkpoint_statuses','final_output']
    raise ValueError('unknown ticket rule')


def persistence(inp,ref,obs):
    before=need(obs.before_state);after=need(obs.after_state)
    expected=ref['expected_outcome'];is_day='day_detail' in inp
    baseline=inp.get('saved_state',{'request':inp.get('request'),'days_detail':[inp.get('day_detail')]})
    if not same(before,baseline):return False,'execution starts from frozen input','input_state_drift',['before_state']
    if expected=='conflict':
        latest=need(obs.latest_state)
        if same(latest,before):return False,'concurrent change captured','no_concurrent_change',['latest_state']
        if is_day:
            changed_day=latest['days_detail'][inp['day_detail']['day_index']]
            if any(meal_slot(m,changed_day['meals'])=='dinner' for m in changed_day['meals']):return False,'concurrent dinner deletion','dinner_still_present',['latest_state']
        elif latest['plan'].get('budget')!=inp['fault']['mutation']['value']:return False,'specified concurrent mutation','unexpected_mutation',['latest_state']
        ok=same(after,latest) and obs.final_output is None and obs.execution_status=='conflict' and obs.http_status==409
    elif not is_day or expected in {'rejected','timeout','cancelled'} or obs.execution_status!='success':
        ok=same(before,after)
        if is_day and expected in {'rejected','timeout','cancelled'}:
            ok=ok and obs.execution_status==expected and obs.http_status==ref['expected_http'] and obs.final_output is None
            if expected=='rejected':ok=ok and need(obs.recovery_count)<=ref['max_recovery']
            if expected=='timeout':ok=ok and need(obs.route_deadline_seconds)<=110
    else:
        final=need(obs.final_output);idx=inp['day_detail']['day_index']
        expected_state={**before,'days_detail':list(before['days_detail'])};expected_state['days_detail'][idx]=final
        ok=same(after,expected_state) and obs.execution_status=='success' and obs.http_status==200
    return ok,'only successful target day may change; failed/late writes preserve captured state',{'before_hash':digest(before),'after_hash':digest(after)},['before_state','latest_state','after_state','final_output']


def trace_check(obs):
    doc=need(obs.trace);rows=doc['spans'];ids=[r['id'] for r in rows];root=doc['operation_id'];bad=[]
    if not rows or len(set(ids))!=len(ids):bad.append('duplicate_or_empty_tree')
    by_id={r['id']:r for r in rows}
    if root not in by_id or sum(r['parent_id'] is None for r in rows)!=1:bad.append('invalid_root')
    calls=need(obs.actual_model_calls)
    if sum(r['name']=='model_call' for r in rows)!=calls:bad.append('model_attempt_count')
    required={'snapshot_read','eligibility'} if obs.case_id.startswith('T') else {'snapshot_read'}
    if obs.execution_status=='success':
        if obs.case_id.startswith('T'):
            if obs.business_outcome=='fallback':required.add('rule_fallback')
            if obs.model_status=='success' and obs.raw_model is not None:required|={'model_selection','output_validation'}
        else:
            required|={'model_suggestion','output_validation','constraint_repair','route_calculation','schedule_validation','fact_projection','cas_save'}
            if obs.business_outcome=='preserved_original':required.add('saved_schedule_recovery')
    if not required <= {r['name'] for r in rows}:bad.append('missing_business_steps')
    for r in rows:
        if not r.get('end_time'):bad.append('unclosed_span');continue
        start,end=datetime.fromisoformat(r['start_time']),datetime.fromisoformat(r['end_time'])
        if end<start:bad.append('negative_span')
        if r.get('facts',{}).get('truncated'):bad.append('truncated_trace')
        if r['parent_id']:
            parent=by_id.get(r['parent_id'])
            if not parent:bad.append('foreign_parent');continue
            if parent.get('end_time') and (start<datetime.fromisoformat(parent['start_time']) or end>datetime.fromisoformat(parent['end_time'])):bad.append('child_outside_parent_time')
            if not r['dotted_order'].startswith(parent['dotted_order']+'.'):bad.append('wrong_dotted_order')
            seen={r['id']};p=parent
            while p:
                if p['id'] in seen:bad.append('cyclic_tree');break
                seen.add(p['id']);p=by_id.get(p['parent_id'])
        usage=r.get('facts',{})
        if usage.get('usage_known'):
            if r['name']!='model_call' or r['run_type']!='llm' or usage.get('total_tokens')!=usage.get('input_tokens',0)+usage.get('output_tokens',0):bad.append('duplicated_or_invalid_usage')
    expected=obs.execution_status
    if root in by_id and by_id[root]['status']!=expected:bad.append('root_status_mismatch')
    if obs.execution_status=='cancelled' and need(obs.external_calls_after_cancel)!=0:bad.append('calls_after_cancel')
    return not bad,'closed isolated tree; actual calls and usage counted once',sorted(set(bad)),['trace','actual_model_calls','external_calls_after_cancel']


def judge_check(rule,obs,calibration):
    value=(obs.judge or {}).get(rule)
    if value is None or value.get('abstain_reason'):raise PendingReference()
    if calibration is None or calibration.judge_version!=value.get('judge_version'):raise PendingReference()
    score=value.get('score');paths=value.get('evidence_paths')
    if type(score) is not int or score not in {0,1,2} or not paths or not value.get('judge_version'):raise MissingEvidence()
    for path in paths:
        if not path.startswith('final_output.'):raise MissingEvidence()
        node=obs.final_output
        try:
            for part in path.split('.')[1:]:node=node[int(part)] if isinstance(node,list) else node[part]
        except (KeyError,IndexError,TypeError,ValueError):raise MissingEvidence() from None
    return score==2,'calibrated semantic score 0/1/2',{'score':score,'normalized':score/2},paths


def evaluate(case,inp,ref,routes,observation,*,allow_provisional=False,judge_calibration=None):
    obs=observation if isinstance(observation,Observation) else Observation.model_validate(observation)
    calibration=JudgeCalibration.model_validate(judge_calibration) if judge_calibration is not None else None
    if obs.case_id!=case.case_id or obs.case_version!=case.case_version or obs.input_sha256!=case.input_sha256:
        raise ValueError('observation belongs to another frozen input/version')
    if digest(inp)!=case.input_sha256 or digest(ref)!=case.reference_sha256:
        raise ValueError('scoring inputs/reference differ from frozen case')
    if obs.provenance not in {case.execution_mode,'scorer_selftest','baseline','replay_model'}:raise ValueError('execution provenance mismatch')
    checks=[]
    for assertion in case.expected_assertions:
        rule,layer=assertion.rule_id,assertion.layer
        provisional=case.annotation.status!='confirmed' and rule in REFERENCE_RULES
        values=dict(rule_id=rule,layer=layer,reference_status=case.annotation.status,provisional=provisional)
        if not assertion.applicable:
            checks.append(Check(**values,status='NOT_APPLICABLE',score=None,reason=assertion.reason));continue
        if provisional and not allow_provisional:
            checks.append(Check(**values,status='NOT_EVALUATED',score=None,reason='reference_pending_human'));continue
        try:
            if rule in {'R-WINDOW','R-INTENT','R-ROUTE'} and case.route_sha256 is not None and (routes is None or digest(routes)!=case.route_sha256):
                raise MissingEvidence()
            if rule.startswith('T-'):ok,expected,actual,paths=ticket_rule(rule,layer,inp,ref,obs)
            elif rule.startswith('R-'):ok,expected,actual,paths=day_constraints(rule,layer,inp,ref,obs,routes)
            elif rule=='S-PERSIST':ok,expected,actual,paths=persistence(inp,ref,obs)
            elif rule=='S-TRACE':ok,expected,actual,paths=trace_check(obs)
            else:ok,expected,actual,paths=judge_check(rule,obs,calibration)
            score=actual['normalized'] if rule.startswith('J-') else float(ok)
            checks.append(Check(**values,status='PASS' if ok else 'FAIL',score=score,expected=expected,actual=actual,evidence_paths=paths,reason='matched' if ok else 'constraint_violation'))
        except PendingReference:
            checks.append(Check(**values,status='NOT_EVALUATED',score=None,reason='reference_or_calibrated_judge_unavailable'))
        except (MissingEvidence,KeyError,IndexError,TypeError,ValueError):
            checks.append(Check(**values,status='ERROR',score=None,reason='required_evidence_missing_or_invalid'))
        except Exception:
            # Evaluator failures retain their slot; no exception text or credential
            # can escape into the report, and other independent rules still run.
            checks.append(Check(**values,status='ERROR',score=None,reason='evaluator_internal_error'))
    hard=[c for c in checks if c.layer=='system' and c.rule_id in HARD_RULES and c.status!='NOT_APPLICABLE']
    return dict(case_id=case.case_id,case_version=case.case_version,target=case.target,split=case.split,data_origin=case.data_origin,
        execution_mode=case.execution_mode,provenance=obs.provenance,run_id=obs.run_id,reference_status=case.annotation.status,
        model_quality_included=case.execution_mode=='live_model_with_replay' and obs.provenance=='live_model_with_replay' and bool(obs.actual_model_calls),
        formal_acceptance=case.annotation.status=='confirmed' and obs.provenance not in {'scorer_selftest','replay_model'} and bool(hard) and all(c.status=='PASS' for c in hard),
        checks=[c.model_dump(mode='json') for c in checks])
