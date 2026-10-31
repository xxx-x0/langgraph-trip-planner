"""Explicit fixture authoring command, never called by the loader or application.

Synthetic examples are agent-authored, not human annotations. Mixed cases require
the already frozen P0 files and validate their manifest before projection.
"""
import argparse
import copy
import hashlib
import itertools
import json
from datetime import datetime
from pathlib import Path
from .contracts import Case, digest

HOLDOUT={'T04','T08','T10','T12','T17','T18','R03','R07','R10','R12'}
FAULTS={'T13','T15','T16','T17','R07','R08','R11','R12'}
NO_MODEL={'T07','T14'}
STAMP='2026-10-24'  # Authored date, not a fabricated precise collection timestamp.


def complete_clock_fields(value):
    """P3 input repair: lossless text projection of existing timeline minute facts."""
    if isinstance(value,dict):
        for item in value.get('timeline_schedule',[]):
            for number,text in [('start_minutes','start_time'),('end_minutes','end_time')]:
                if number in item and text not in item:
                    minutes=item[number];item[text]=f'{minutes//60:02d}:{minutes%60:02d}'
        for child in value.values():complete_clock_fields(child)
    elif isinstance(value,list):
        for child in value:complete_clock_fields(child)


def write(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf-8')


def keep(value,keys):
    return {k:copy.deepcopy(value[k]) for k in keys.split() if k in value}


def project_day(day):
    if day is None:return None
    d=keep(day,'day_index date day_start_time timeline_order locked_attraction_names removed_attraction_names is_assembled overnight_stay companion_count rest_periods travel_window')
    d['attractions']=[dict(keep(a,'name address location visit_duration category rating poi_id ticket_price open_hours'),description='') for a in day['attractions']]
    d['meals']=[keep(m,'type category name address location cuisine rating avg_cost distance poi_id source estimated_cost open_hours schedule_mode preferred_slot') for m in day['meals']]
    d['hotel']=keep(day['hotel'],'name address location estimated_cost price currency hotel_id') if day.get('hotel') else None
    d['route_segments']=[keep(r,'from_name to_name distance duration mode is_estimated') for r in day.get('route_segments',[])]
    d['timeline_schedule']=[keep(t,'kind ref_name start_minutes end_minutes start_time end_time duration phase') for t in day.get('timeline_schedule',[])]
    d['description']='';d['meal_adjustments']=[]
    return d


def project_request(req):
    return keep(req,'city start_date end_date travel_days transportation accommodation companions hotel_occupancy default_day_start_time journey rest_periods')


def request(city='苏州',start='2027-04-12',end='2027-04-15'):
    return dict(city=city,start_date=start,end_date=end,travel_days=(datetime.fromisoformat(end)-datetime.fromisoformat(start)).days+1,
                transportation='公共交通',accommodation='经济型酒店',companions={'count':2,'type':'friends'})


def ticket(cid, letter,dep='12:00',arr='13:00',price=120,day='2027-04-12',mode='train',available='available'):
    return dict(id=f'SYN_{cid}_{letter}',mode=mode,service=f'SYN_{cid}_{letter}',from_station='南京南' if mode=='train' else '南京禄口',
        to_station='苏州站' if mode=='train' else '上海虹桥',departure=day+'T'+dep,arrival=day+'T'+arr,seat='二等座' if mode=='train' else '经济舱',
        fare_per_person=price,availability=available,source='12306' if mode=='train' else 'ctrip')


def leg(candidate,buffers):
    return dict(mode=candidate['mode'],departure_station=candidate['from_station'],arrival_station=candidate['to_station'],
        departure_time=candidate['departure'],arrival_time=candidate['arrival'],passengers=2,ticket_total=None,price_source='unknown',**buffers)


def minute(text):
    return int(text[:2])*60+int(text[3:5])


def clock(n):return f'{n//60:02d}:{n%60:02d}'


def scheduled_day(day,start,end,name='SYN_保留活动'):
    a=dict(name=name,address='人工测试地点',description='',visit_duration=end-start,ticket_price=None,open_hours='00:00-23:59')
    return dict(day_index=0,date=day,day_start_time=clock(start),attractions=[a],meals=[],hotel=None,
        timeline_order=[{'kind':'attraction','ref_name':name}],timeline_schedule=[dict(kind='attraction',ref_name=name,start_minutes=start,end_minutes=end,duration=end-start)],
        route_segments=[],locked_attraction_names=[name],removed_attraction_names=[],rest_periods=[])


def multi_seed(cid, candidates):
    buffers=dict(transfer_before_minutes=30,station_buffer_minutes=30,transfer_after_minutes=30,baggage_minutes=0,lodging_buffer_minutes=30)
    plan=dict(title='人工换城边界样本',start_date='2027-04-12',end_date='2027-04-16',origin={'id':'o','name':'南京'},destination={'id':'d','name':'南京'},
        companions={'count':2,'type':'friends'},stops=[dict(id='a',city={'id':'sz','name':'苏州'},start_date='2027-04-12',end_date='2027-04-14'),
        dict(id='b',city={'id':'hz','name':'杭州'},start_date='2027-04-14',end_date='2027-04-16')],
        transfers=[dict(from_stop='a',to_stop='b',leg=leg(candidates[1],buffers))])
    # Departure consumes transfer_before + station + lodging; use no lodging here.
    buffers['lodging_buffer_minutes']=0;buffers['transfer_after_minutes']=60
    plan['transfers'][0]['leg'].update(buffers)
    snapshots={}
    for stop,start,end in [('a',960,1020),('b',1200,1260)]:
        req=request('苏州' if stop=='a' else '杭州','2027-04-12' if stop=='a' else '2027-04-14','2027-04-14' if stop=='a' else '2027-04-16')
        d=scheduled_day('2027-04-14',start,end,'SYN_'+cid+'_'+stop)
        days=[None,None,d] if stop=='a' else [d,None,None]
        d['day_index']=2 if stop=='a' else 0
        snapshots[stop]=dict(request=req,days_detail=days,draft_id='eval_'+cid+'_'+stop)
    return dict(kind='multi_city_v1',id='mc_eval_'+cid,revision=1,status='draft',plan=plan,snapshots=snapshots),buffers


def ticket_case(n):
    cid=f'T{n:02d}';day='2027-04-12';priority={1:'price',2:'time',3:'daytime',5:'price',6:'price',8:'price',13:'price'}.get(n,'balanced')
    cs=[ticket(cid,l,price=p) for l,p in zip('ABC',[120,180,260])]
    if n==2:cs=[ticket(cid,l,'12:00',arr,180) for l,arr in zip('ABC',['13:30','13:00','14:00'])]
    if n==3:cs=[ticket(cid,l,dep,arr,180) for l,dep,arr in [('A','06:40','08:00'),('B','08:00','09:20'),('C','21:30','23:00')]]
    if n==4:cs=[ticket(cid,l,'12:00',arr,p) for l,arr,p in [('A','13:00',180),('B','13:30',120),('C','13:00',220)]]
    if n==5:cs=[ticket(cid,l,price=p) for l,p in [('A',120),('B',None),('C',180)]]
    if n==6:cs=[ticket(cid,l,price=p,available=a) for l,p,a in [('A',80,'unavailable'),('B',90,'waitlist'),('C',120,'available'),('D',180,'unknown')]]
    if n==7:cs=[ticket(cid,'A',available='unavailable'),ticket(cid,'B',available='waitlist')]
    if n==13:cs=cs[:2]
    direction='outbound';window={};buffers={k:0 for k in ['transfer_before_minutes','station_buffer_minutes','transfer_after_minutes','baggage_minutes','lodging_buffer_minutes']}
    req=request();days=[None]*4
    if n in {9,12,14,15}:
        direction='inbound';day='2027-04-15'
        if n==9:
            cs=[ticket(cid,l,t,'20:00',day=day) for l,t in zip('ABCD',['17:40','18:00','18:30','18:31'])]
            buffers.update(transfer_before_minutes=45,station_buffer_minutes=45);end=990
        elif n==12:
            cs=[ticket(cid,'A','23:00','01:00',day=day),ticket(cid,'B','18:00','20:00',day=day)];cs[0]['arrival']='2027-04-16T01:00';end=960
        else:
            cs=[ticket(cid,'A','16:00' if n==14 else '18:00','19:00',day=day),ticket(cid,'B','17:00','20:00',day=day)]
            buffers.update(transfer_before_minutes=30,station_buffer_minutes=30);end=1020
        days[3]=scheduled_day(day,end-60,end,'SYN_'+cid+'_活动');days[3]['day_index']=3
        window['departure_after']=day+'T'+clock(end+buffers['transfer_before_minutes']+buffers['station_buffer_minutes'])
    if n==10:
        cs=[ticket(cid,l,'07:00',a,day=day,mode='flight') for l,a in [('A','08:50'),('B','09:10')]]
        req['city']='上海';days[0]=scheduled_day(day,660,720,'SYN_T10_活动')
        buffers.update(baggage_minutes=40,transfer_after_minutes=60,lodging_buffer_minutes=20)
        window['arrival_before']=day+'T09:00'
    if direction=='inbound':
        for c in cs:c.update(from_station='苏州站',to_station='南京南')
    req['journey']=dict(origin_city='南京',return_city='南京',**{direction:leg(cs[1] if n==12 else cs[0],buffers)})
    q=dict(mode=cs[0]['mode'],direction=direction,from_place='南京' if direction=='outbound' else '苏州',to_place=req['city'] if direction=='outbound' else '南京',date=day,passengers=2,priority=priority)
    inp=dict(query=q,candidates=cs,context=dict(kind='draft',draft_id='eval_'+cid,request=req,days_detail=days),
        saved_state={'request':req,'days_detail':days},fault=None)
    if n==8:inp['context']=None
    if n in {11,17}:
        day='2027-04-14'
        cs=[ticket(cid,l,dep,arr,day=day) for l,dep,arr in [('A','18:00','20:00'),('B','18:15','19:00'),('C','17:30','18:15')]]
        for c in cs:c.update(from_station='苏州站',to_station='杭州东')
        doc,buffers=multi_seed(cid,cs);inp.update(candidates=cs,saved_state=doc,context=dict(kind='multi',draft_id=doc['id'],revision=1,from_stop='a',to_stop='b'))
        inp['query'].update(date=day,from_place='苏州',to_place='杭州')
        window=dict(departure_after=day+'T18:00',arrival_before=day+'T19:00')
    bounds=dict(start_date='2027-04-12',end_date='2027-04-16' if n in {11,17} else '2027-04-15',**window)
    checks=[]
    for c in inp['candidates']:
        reasons=[];margins=[]
        if c['availability'] in {'unavailable','waitlist'}:reasons.append('not_available')
        if c['arrival'][:10]>bounds['end_date']:reasons.append('outside_trip_dates')
        if window.get('departure_after'):
            margin=int((datetime.fromisoformat(c['departure'])-datetime.fromisoformat(window['departure_after'])).total_seconds()/60);margins.append(margin)
            if margin<0:reasons.append('departure_conflict')
        if window.get('arrival_before'):
            margin=int((datetime.fromisoformat(window['arrival_before'])-datetime.fromisoformat(c['arrival'])).total_seconds()/60);margins.append(margin)
            if margin<0:reasons.append('arrival_conflict')
        checks.append(dict(candidate_id=c['id'],eligible=not reasons,reasons=reasons,margins=margins,tight=bool(margins) and 0<=min(margins)<=30))
    eligible=[c['candidate_id'] for c in checks if c['eligible']]
    first={2:['B'],3:['B'],4:['A','B'],6:['C'],9:['B','C','D'],10:['A'],11:['B'],12:['B']}.get(n,['A'])
    acceptable=[f'SYN_{cid}_{x}' for x in first if f'SYN_{cid}_{x}' in eligible]
    expected='empty_unavailable' if n==7 else 'empty_conflict' if n==14 else 'fallback' if n in {13,15} else 'cancelled' if n==16 else 'conflict' if n==17 else 'recommended'
    if n==13:inp['fault']=dict(kind='invalid_model_id',barrier='after_filter_before_validation',response={'ids':['SYN_X']})
    if n==15:inp['fault']=dict(kind='model_timeout',barrier='inside_model_call',exception='ExternalServiceError:timeout',max_attempts=1)
    if n==16:inp['fault']=dict(kind='cancel',barrier='model_entered',resume='cancel_task')
    if n==17:inp['fault']=dict(kind='concurrent_change',barrier='model_entered',mutation={'path':'plan.budget','value':9999},checkpoints=['old_recommendation','old_basis_preview'])
    return inp,dict(expected_outcome=expected,expected_http=409 if n==17 else None if n==16 else 200,
        eligible_ids=eligible,candidate_checks=checks,bounds=bounds,buffer_fields=buffers,acceptable_first=acceptable,
        rank_key='price' if n in {1,5,8,13} else 'duration' if n==2 else None,
        preferred_pairs=[[f'SYN_{cid}_A',f'SYN_{cid}_C']] if n==4 else [],
        expected_ticket_total=None,checkpoint_statuses={'old_recommendation':409,'old_basis_preview':409} if n==17 else {},
        method='Independent date/interval arithmetic; candidate preference specification; no production evaluator called')


def synth_day(n):
    cid=f'R{n:02d}';names={x:f'SYN_{cid}_{x}' for x in 'ABCLDQH'}
    attrs=[dict(name=names[x],address='人工测试地点',description='',visit_duration=60,ticket_price=None,
        open_hours='08:00-21:00',location={'longitude':120.5+i*.01,'latitude':31.3+n*.001}) for i,x in enumerate('ABC')]
    def meal(x,slot):return dict(name=names[x],type=slot,category='main',address='人工餐厅',location={'longitude':120.55+(x=='D')*.01,'latitude':31.3+n*.001},
        avg_cost=40 if x=='L' else 55,estimated_cost=40 if x=='L' else 55,source='nearby',poi_id=names[x],open_hours='10:00-22:00',schedule_mode='auto',preferred_slot=slot)
    lunch,dinner=meal('L','lunch'),meal('D','dinner');alternative=meal('Q','lunch')
    if n==3:lunch['schedule_mode']='manual'
    if n==6:lunch['name']=names['L']=f'SYN_{cid}_P';lunch['poi_id']=names['L']
    if n==7:alternative.update(type='dinner',preferred_slot='dinner',open_hours='10:00-17:00')
    if n==8:lunch['open_hours']=alternative['open_hours']='08:00-11:00'
    meals=[lunch] if n==5 else [lunch,dinner]
    hotel=dict(name=names['H'],address='人工酒店',location={'longitude':120.5,'latitude':31.3+n*.001},estimated_cost=0,quote=None)
    day=dict(day_index=0,date='2027-04-12',day_start_time='09:00',attractions=attrs,meals=meals,hotel=hotel,
        locked_attraction_names=[names['B']] if n==2 else [],removed_attraction_names=[f'SYN_{cid}_REMOVED'] if n==3 else [],
        timeline_order=[],timeline_schedule=[],route_segments=[],rest_periods=[],is_assembled=True,companion_count=2,meal_adjustments=[],description='人工夹具')
    rest=[]
    if n==9:rest=[dict(id='SYN_R09_REST',date=day['date'],start_time='14:00',end_time='15:00',label='当前区域休息')]
    day['rest_periods']=rest
    pool=[alternative,dinner] if n in {6,7,8} else [lunch,dinner]
    nodes=list(dict.fromkeys([a['name'] for a in attrs]+[m['name'] for m in meals+pool]+[hotel['name']]))
    edges=[dict(edge_id=f'{cid}-{i:02d}',**{'from':a,'to':b},mode='步行',duration_minutes=5,duration_seconds=300,
        distance_m=300,is_estimated=False,source='synthetic',collected_at=None) for i,(a,b) in enumerate(itertools.permutations(nodes,2))]
    windows={a['name']:[[480,1260]] for a in attrs}
    for m in meals+pool:windows[m['name']]=[[minute(m['open_hours'][:5]),minute(m['open_hours'][-5:])]]
    hard=dict(start_minutes=540,end_latest=1140 if n==9 else 1320,opening_windows=windows,last_entry_deadlines={},
        lunch_start_range=[690,870],dinner_start_range=[1050,1290],rest_periods=rest)
    initial=['A','B','L','C'] if n==3 else ['A','L','B','C']
    if n!=5:initial+=['D']
    day['timeline_order']=[dict(kind='hotel',ref_name=hotel['name'],phase='start')]+[dict(kind='attraction' if x in 'ABC' else 'meal',ref_name=names[x]) for x in initial]+[dict(kind='hotel',ref_name=hotel['name'],phase='end')]
    if n==9:
        # Departure-day fixture: no overnight hotel task after dinner.
        day['hotel']=None;day['overnight_stay']=False
        day['timeline_order']=[x for x in day['timeline_order'] if x['kind']!='hotel']
    timeline=reference_timeline(day,edges,hard)
    day['timeline_schedule']=timeline
    seq=[x['ref_name'] for x in day['timeline_order']]
    day['route_segments']=[dict(from_name=a,to_name=b,mode='步行',duration='5分钟',distance='300米',is_estimated=False) for a,b in zip(seq,seq[1:])]
    hint={1:'先去 B 再去 A，C 仍放最后，午晚餐不变',2:'C 尽量提前，尊重 B 的锁定位置',3:'优化现有景点顺序，别改我的手动午餐',4:'把景点按 B、A、C 调整，保留正餐',5:'顺路调整一下，不新增用餐',6:'从当前或备选里选顺路餐厅',7:'将备选 Q 安排为 18:00 晚餐',8:'调整景点，保留已有正餐',9:'把 A、B 对调，C 仍在最后，休息与两餐保持',11:'调整景点顺序',12:'调整顺序，保留当前正餐'}[n]
    for x in ['A','B','C','Q']:hint=hint.replace(x,names[x])
    target=[names[x] for x in ('CBA' if n==2 else 'BAC')] if n in {1,2,4,9} else None
    ref=dict(expected_outcome='rejected' if n==8 else 'timeout' if n==11 else 'conflict' if n==12 else 'preserved_original' if n==7 else 'adjusted',
        expected_http={8:422,11:504,12:409}.get(n,200),hard_constraints=hard,expected_order=target,
        intent_kind='exact_order' if target else 'preserve_constraints',baseline_traffic_minutes=len(edges[:len(seq)-1])*5,
        required_route_improvement=False,acceptable_first=None,max_recovery=1,
        method='Explicit synthetic constraints and independent interval construction; human confirmation pending')
    fault=None
    if n==7:fault=dict(kind='invalid_meal_window',barrier='model_response',response={'attractions_order':[a['name'] for a in attrs],'meals':[dict(lunch),dict(alternative,insert_after=names['C'])]})
    if n==8:fault=dict(kind='unrecoverable_meal_window',barrier='model_response',response={'attractions_order':[a['name'] for a in attrs],'meals':copy.deepcopy(meals)})
    if n==11:fault=dict(kind='route_timeout',barrier='route_entered',deadline_seconds=110,clock='controlled',cancel_child=True)
    if n==12:fault=dict(kind='concurrent_delete_meal',barrier='model_entered',remove_slot='dinner',checkpoints=['cas_save'])
    req=request()
    if n==9:
        req=request(end='2027-04-12');req['rest_periods']=rest
        c=ticket(cid,'RETURN','20:00','21:00')
        req['journey']=dict(origin_city='南京',return_city='南京',inbound=leg(c,dict(transfer_before_minutes=30,station_buffer_minutes=30,transfer_after_minutes=0,baggage_minutes=0,lodging_buffer_minutes=0)))
        day['travel_window']={'start_minutes':480,'end_minutes':1140}
    return dict(request=req,day_detail=day,dining_candidates=pool,hint=hint,fault=fault),ref,dict(schema_version='route-fixture-v1',coverage='all_directed_pairs_within_declared_nodes',nodes=nodes,edges=edges)


def reference_timeline(day,edges,hard):
    """Fixture construction only. The scorer separately checks supplied intervals."""
    by_edge={(e['from'],e['to']):e for e in edges};places={x['name']:x for x in day['attractions']+day['meals']}
    now=hard['start_minutes'];rows=[];order=day['timeline_order'];rests=hard.get('rest_periods',[])
    def append(kind,name,duration,earliest=0):
        nonlocal now
        now=max(now,earliest)
        for r in rests:
            start,end=minute(r['start_time']),minute(r['end_time'])
            if now<end and now+duration>start:
                if not any(x['kind']=='rest' and x['ref_name']==r['id'] for x in rows):rows.append(dict(kind='rest',ref_name=r['id'],start_minutes=start,end_minutes=end,duration=end-start))
                now=end
        rows.append(dict(kind=kind,ref_name=name,start_minutes=now,end_minutes=now+duration,duration=duration));now+=duration
    for index,current in enumerate(order):
        if index==0 and current['kind']=='hotel':continue
        if index:
            before=order[index-1];e=by_edge[before['ref_name'],current['ref_name']]
            append('travel',before['ref_name']+' → '+current['ref_name'],e['duration_minutes'])
        name=current['ref_name'];kind=current['kind']
        if kind=='hotel':append('hotel',name,30)
        else:
            p=places[name];earliest=0
            if kind=='meal':earliest=hard['lunch_start_range' if p['type']=='lunch' else 'dinner_start_range'][0]
            append(kind,name,p['visit_duration'] if kind=='attraction' else 60,earliest)
    return sorted(rows,key=lambda r:r['start_minutes'])


def matrix(cid, inp, ref):
    ticket_target=cid.startswith('T');result=[];success=ref['expected_outcome'] in {'recommended','fallback','adjusted','preserved_original'}
    rules=['T-VALID','T-ELIG','T-FACT','T-MARGIN','T-RANK','T-DISCLOSE','T-OUTCOME'] if ticket_target else ['R-LOCK','R-REMOVED','R-MANUAL','R-MEAL','R-FACT','R-DURATION','R-REST','R-WINDOW','R-INTENT','R-ROUTE','R-DISCLOSE']
    dual={'T-VALID','T-RANK','R-LOCK','R-REMOVED','R-MEAL','R-INTENT'}
    for rule in rules:
        for layer in (['model','system'] if rule in dual else ['system']):
            applicable=True;reason='required by frozen scenario'
            if layer=='model' and (cid in NO_MODEL or cid in {'T15','T16','R11'}):applicable=False;reason='no completed model suggestion expected at this checkpoint'
            if layer=='system' and not success and rule not in {'T-ELIG','T-DISCLOSE','T-OUTCOME'}:applicable=False;reason='expected rejection/cancellation has no final output; persistence evaluated separately'
            if rule=='T-MARGIN' and not (ref.get('bounds',{}).get('departure_after') or ref.get('bounds',{}).get('arrival_before')):applicable=False;reason='no constrained arrival/departure interval'
            if rule=='T-RANK' and cid in FAULTS:applicable=False;reason='injected output is not a model quality ranking experiment'
            if rule=='R-LOCK' and not inp['day_detail']['locked_attraction_names']:applicable=False;reason='no locked attraction'
            if rule=='R-MANUAL' and not any(m.get('schedule_mode')=='manual' for m in inp['day_detail']['meals']):applicable=False;reason='no manual meal'
            if rule=='R-REST' and not inp['day_detail'].get('rest_periods'):applicable=False;reason='no fixed rest period'
            if rule=='R-ROUTE' and cid!='R10':applicable=False;reason='no required route improvement in this scenario'
            if rule=='R-INTENT' and cid in FAULTS:applicable=False;reason='fault injection validates protections, not model quality'
            result.append(dict(rule_id=rule,layer=layer,applicable=applicable,reason=reason))
    result += [dict(rule_id=r,layer=l,applicable=True,reason='operation evidence required') for r,l in [('S-PERSIST','system'),('S-TRACE','observability')]]
    if cid in {'T04','R10'}:
        result += [dict(rule_id=r,layer='judge',applicable=True,reason='optional semantic score; human calibration pending') for r in (['J-TRADEOFF'] if cid=='T04' else ['J-INTENT','J-TRADEOFF'])]
    return result


def build(output, p0):
    manifest=json.loads((p0/'manifest.json').read_text())
    # P0 checksums cover raw source archives as well as selected fixtures.
    frozen=manifest['files']
    if isinstance(frozen,list):frozen={f['path']:f for f in frozen}
    for name in ['T18-input','T18-reference','R10-input','R10-reference']:
        rel='fixtures/'+name+'.json';entry=frozen[rel]
        assert hashlib.sha256((p0/rel).read_bytes()).hexdigest()==entry['sha256'], 'P0 source changed'
    cases=[]
    titles=['低价优先','车程优先','日间优先','均衡并列首选','未知价不当免费','无票与未知余票','全部无票','无上下文兼容','离城余量边界','抵达缓冲边界','双城窗口','跨出旅行日期','非法候选回退','全部日程冲突','模型超时回退','取消传播','双检查点过期拒绝','旧日程与补采铁路候选']
    rtitles=['明确交换顺序','锁定第二景点','删除与手动午餐','保留两顿正餐','不恢复已删晚餐','餐厅事实来源','关闭餐厅修正','无法保留正餐拒绝','固定休息与抵离窗口','旧日程与补采路线改善','路线共享期限','并发删除晚餐']
    for prefix,total in [('T',18),('R',12)]:
        for n in range(1,total+1):
            cid=f'{prefix}{n:02d}';routes=None;origin='synthetic'
            sources=[dict(source_id=cid+'-authored',origin='synthetic',component='entire_fixture',author='codex',constructed_at=STAMP,note='Agent-authored artificial data; not human supplied or human annotated')]
            if cid not in {'T18','R10'}:
                if prefix=='T':inp,ref=ticket_case(n)
                else:inp,ref,routes=synth_day(n)
            else:
                original=json.loads((p0/f'fixtures/{cid}-input.json').read_text());gold=json.loads((p0/f'fixtures/{cid}-reference.json').read_text())
                sources=[dict(source_id=cid+'-historical',origin='historical_capture',component='itinerary_and_public_POI_facts',original_date='2026-10-20' if cid=='T18' else '2026-10-14',revalidated=False),
                    dict(source_id=cid+'-supplement',origin='new_capture',component='ticket_candidates' if cid=='T18' else 'route_matrix',collected_at='2026-10-24',provider='12306' if cid=='T18' else 'amap',note='Collected in P0, not collected again in P2')]
                for src in sources:src['upstream_manifest_sha256']=hashlib.sha256((p0/'manifest.json').read_bytes()).hexdigest()
                lineage=manifest['cases'][cid]
                sources[0].update(sha256=lineage['historical_snapshot']['sha256'],bytes=lineage['historical_snapshot']['bytes'],
                    archive_relative_path=f'raw/{cid}-historical-snapshot.json',date_kind='archive_date_not_per_field_query_time')
                raw_names=[p for p in frozen if p.startswith(f'raw/{cid}-') and 'historical' not in p]
                sources[1]['raw_files']=[dict(archive_relative_path=p,sha256=frozen[p]['sha256'],bytes=frozen[p]['bytes']) for p in sorted(raw_names)]
                if cid=='T18':sources[1].update(collected_at=lineage['candidate_capture_at'],dom_rows=156,supported_available_rows=128,frozen_candidates=80,synthetic_candidates=0)
                else:sources[1].update(collected_at=lineage['route_capture_start'],collection_end=lineage['route_capture_end'],new_missing_edges=15,refreshed_control_edges=8,synthetic_routes=0,original_travel_date='2026-10-15')
                if cid=='T18':
                    origin='mixed_historical_itinerary_and_new_capture';doc=original['saved_document']
                    plan=keep(doc['plan'],'start_date end_date origin destination companions hotel_occupancy budget pace transportation accommodation stops transfers')
                    plan['title']='EVAL T18 historical projection'
                    for s in plan['stops']:
                        s.pop('notes',None)
                        for l in s.get('lodgings',[]):
                            for k in ['source_note','notes']:l.pop(k,None)
                    for t in plan['transfers']:
                        for k in ['price_note','baggage_policy','refund_policy']:t['leg'][k]=''
                        t['leg'].update(ticket_total=None,price_source='unknown',quoted_at=None,quote_expires_at=None)
                    snapshots={k:dict(request=project_request(v['request']),days_detail=[project_day(d) for d in v['days_detail']],draft_id='eval_T18_'+k) for k,v in doc['snapshots'].items()}
                    inp=dict(query=original['query'],candidates=original['candidates'],context=dict(original['context'],draft_id='mc_eval_T18'),
                        saved_state=dict(id='mc_eval_T18',kind=doc['kind'],revision=doc['revision'],status='draft',plan=plan,snapshots=snapshots),fault=None)
                    oldleg=next(t['leg'] for t in plan['transfers'] if t['from_stop']==inp['context']['from_stop'] and t['to_stop']==inp['context']['to_stop'])
                    ref=dict(expected_outcome='recommended',expected_http=200,eligible_ids=gold['eligible_ids'],candidate_checks=[dict(candidate_id=c['candidate_id'],eligible=c['eligible'],reasons=c['reason_codes'],margins=[c['margin_minutes']],tight=c['tight']) for c in gold['candidate_checks']],
                        bounds={'start_date':plan['start_date'],'end_date':plan['end_date'],'departure_after':'2026-11-01T15:45'},
                        buffer_fields=keep(oldleg,'transfer_before_minutes station_buffer_minutes transfer_after_minutes baggage_minutes lodging_buffer_minutes'),
                        acceptable_first=None,rank_key=None,preferred_pairs=[],expected_ticket_total=None,checkpoint_statuses={},
                        method=gold['method'],ranking_status='pending_human_no_gold',source_limitations=gold['source_limitations'])
                else:
                    origin='mixed_historical_day_and_new_route_capture';day=project_day(original['day_detail'])
                    inp=dict(request=dict(request(start=day['date'],end=day['date']),companions={'count':1,'type':'solo'}),day_detail=day,
                        dining_candidates=copy.deepcopy(day['meals']),hint=original['hint'],fault=None)
                    edges=[keep(e,'edge_id from to mode duration_seconds duration_minutes duration_rounding distance_m is_estimated source collected_at historical_comparison_role') for e in original['route_matrix']]
                    routes=dict(schema_version='route-fixture-v1',coverage='20_declared_lock_preserving_interleavings_only',nodes=sorted({e['from'] for e in edges}|{e['to'] for e in edges}),edges=edges,allowed_changes=original['allowed_changes'])
                    ref=dict(expected_outcome='adjusted',expected_http=200,hard_constraints=gold['hard_constraints'],expected_order=None,intent_kind='route_improvement',
                        baseline_traffic_minutes=gold['frozen_baseline']['traffic_minutes'],historical_baseline_minutes_archive_only=gold['historical_baseline_minutes'],
                        required_route_improvement=True,acceptable_permutations=gold['acceptable_improvements'],permutations=gold['permutations'],frozen_baseline=gold['frozen_baseline'],max_recovery=1,
                        method=gold['method'],source_limitations=gold['limits'])
                for name in ['input','reference']:
                    rel=f'fixtures/{cid}-{name}.json'
                    sources.append(dict(source_id=cid+'-p0-'+name,origin='projection_lineage',component=name,sha256=frozen[rel]['sha256'],archive_relative_path=rel))
            ip=f'inputs/{cid}.json';rp=f'references/{cid}.json';route_path=f'routes/{cid}.json' if routes else None
            complete_clock_fields(inp)
            write(output/ip,inp);write(output/rp,ref)
            if routes:write(output/route_path,routes)
            case=Case(case_id=cid,case_version='1.0.1-draft',title=(titles if prefix=='T' else rtitles)[n-1],target='ticket_recommendation' if prefix=='T' else 'day_rearrangement',
                split='holdout' if cid in HOLDOUT else 'dev',family='ltp27-suhang-20261020' if cid=='T18' else 'meal-recovery-suzhou-20261014' if cid=='R10' else 'synthetic-ticket-template-v1' if prefix=='T' else 'synthetic-day-template-v1',
                execution_mode='injected_failure' if cid in FAULTS else 'no_model' if cid in NO_MODEL else 'live_model_with_replay',data_origin=origin,sources=sources,
                clock='2026-10-24T19:40:00+08:00' if cid in {'T18','R10'} else '2027-04-01T12:00:00+08:00',random_seed=20261024,
                input_path=ip,reference_path=rp,route_path=route_path,input_sha256=digest(inp),reference_sha256=digest(ref),route_sha256=digest(routes) if routes else None,
                expected_assertions=matrix(cid,inp,ref),annotation=dict(pending_items=['scenario_and_reference_review']+(['acceptable_first_set'] if cid=='T18' else ['opening_windows_and_route_quality'] if cid=='R10' else []),rationale='Agent-authored or independently calculated draft; no human confirmation has been received'),
                limitations=['Not executed against a live model in P2','Scenario holdout only; shared synthetic templates and source-family leakage require review before any unseen-quality claim']+
                    (['Historic itinerary facts are not revalidated; supplement date differs from historical travel date'] if cid in {'T18','R10'} else ['Artificial values are not supplier observations']))
            write(output/f'cases/{cid}.json',case.model_dump(mode='json'));cases.append(case)
    files={str(p.relative_to(output)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(output.rglob('*.json')) if p.name!='manifest.json'}
    write(output/'manifest.json',dict(schema_version='dataset-manifest-v1',dataset_names=['trip-ticket-v1','trip-rearrange-v1'],version='1.0.0-draft',
        status='FROZEN_INPUTS_PENDING_HUMAN_REFERENCES',case_ids=[c.case_id for c in cases],counts=dict(total=30,ticket=18,rearrange=12,dev=20,holdout=10,synthetic=28,mixed=2,live_model_with_replay=20,injected_failure=8,no_model=2),
        source_manifest_sha256=hashlib.sha256((p0/'manifest.json').read_bytes()).hexdigest(),content_sha256=digest(files),files=files,
        uploaded_to_langsmith=False,formal_experiments_run=False,split_review='pending_human_source_family_review'))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--p0',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args()
    if a.output.exists() and any(a.output.iterdir()):p.error('output must be new/empty; frozen versions are never overwritten')
    build(a.output,a.p0)
