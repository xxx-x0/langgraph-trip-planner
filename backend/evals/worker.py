"""One disposable process/SQLite per slot. Never reads reference answers."""
import asyncio
import copy
import json
import os
from pathlib import Path
import re
import sys
import time
from contextlib import ExitStack, asynccontextmanager
from datetime import datetime, timedelta
from unittest.mock import patch


def dump(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False)+'\n')


def trace_origin(origin):
    if origin in {'mixed_historical_day_and_new_route_capture','mixed_historical_itinerary_and_new_capture'}:return 'mixed'
    return origin if origin in {'synthetic','historical_capture','mixed'} else 'unclassified'


def guard(directory, *, live=False):
    """Worker accepts only a fresh local DB. Parent env and dotenv cannot select it."""
    expected = 'sqlite+aiosqlite:///'+str(directory/'case.sqlite')
    if os.environ.get('DATABASE_URL') != expected or (directory/'case.sqlite').exists():
        raise RuntimeError('fresh isolated database required')
    import dotenv
    dotenv.load_dotenv = lambda *a, **kw: False
    # Only the direct DeepSeek endpoint is allowed in an explicitly approved live worker.
    import socket
    allowed=set();original_dns=socket.getaddrinfo
    def resolve(host,*args,**kwargs):
        if not live or host not in {'api.deepseek.com',b'api.deepseek.com'}:
            raise PermissionError('unapproved eval endpoint')
        rows=original_dns(host,*args,**kwargs)
        allowed.update(row[4][0] for row in rows)
        return rows
    socket.getaddrinfo=resolve
    def audit(event, args):
        if event=='socket.getaddrinfo' and (not live or args[0] not in {'api.deepseek.com',b'api.deepseek.com'}):
            raise PermissionError('eval worker network disabled')
        if event in {'socket.connect','socket.sendto'}:
            address=args[1] if event=='socket.connect' else args[-1]
            if not live or not isinstance(address,tuple) or address[0] not in allowed or address[1]!=443:
                raise PermissionError('unapproved eval socket')
        if event=='sqlite3.connect' and str(args[0])!=str(directory/'case.sqlite'):
            raise PermissionError('eval database outside disposable slot')
        if event == 'open' and isinstance(args[0], (str, bytes)):
            p = Path(os.fsdecode(args[0])).resolve()
            if p.name == '.env' or 'references' in p.parts:
                raise PermissionError('worker cannot read credentials or references')
    sys.addaudithook(audit)


async def execute(job, directory):
    from fastapi import HTTPException
    from langchain_core.messages import AIMessage
    from sqlalchemy import select
    from app import database
    from app.models.db_models import TripDraft
    from app.models.schemas import MacroPlan, DaySkeleton, TripRequest, DayDetail, RouteSegment
    from app.services import observability as trace, trip_draft_service as drafts, multicity
    from app.services import ticket_assistant as ticket, ticket_schedule
    from app.api.routes import trip_draft as day_api
    from app.services.external_calls import ExternalServiceError, FailureKind, operation_deadline
    from app.services.journey_service import travel_window
    from .budget import CallBudget, BudgetStop, message_payload

    inp=job['inputs']; cid=job['case']['case_id']; variant=job['variant']; is_day=cid.startswith('R')
    fault=inp.get('fault') if variant!='baseline' else None
    live=variant=='current_live' and not fault and job['case']['execution_mode']=='live_model_with_replay'
    state=copy.deepcopy(inp.get('saved_state') if not is_day else {'request':inp['request'],'days_detail':[inp['day_detail']]})
    draft_id=(inp.get('context') or {}).get('draft_id','eval_'+cid)
    await database.init_db()
    if state:
        if not is_day and (inp.get('context') or {}).get('kind')=='multi':
            payload=dict(id=draft_id,user_id='eval',status='multi_city',request_json=json.dumps(state),selected_attractions_json='[]',macro_plan_json='{}',clusters_data_json='[]',hotels_by_day_json='[]',dining_pool_json='[]',days_detail_json='[]',weather_info_json='[]')
        else:
            req=state['request']; days=state['days_detail']; n=req['travel_days']
            macro=MacroPlan(city=req['city'],total_days=n,days=[DaySkeleton(day_index=j,date=(datetime.fromisoformat(req['start_date'])+timedelta(days=j)).date().isoformat(),attraction_names=[a['name'] for a in (days[j] or {}).get('attractions',[])] if j<len(days) else []) for j in range(n)])
            clusters=[];hotels=[];pools=[]
            for j in range(n):
                detail=days[j] if j<len(days) and days[j] else {}
                clusters.append([{**a,'visit_minutes':a['visit_duration'],**(a.get('location') or {})} for a in detail.get('attractions',[])])
                hotels.append([detail['hotel']] if detail.get('hotel') else [])
                pools.append({'main':inp.get('dining_candidates',[]) if is_day else []})
            payload=dict(id=draft_id,user_id='eval',status='assembling',request_json=json.dumps(req),selected_attractions_json='[]',macro_plan_json=macro.model_dump_json(),clusters_data_json=json.dumps(clusters),hotels_by_day_json=json.dumps(hotels),dining_pool_json=json.dumps(pools),days_detail_json=json.dumps(days),weather_info_json='[]')
        async with database.async_session() as session:
            session.add(TripDraft(**payload)); await session.commit()

    async def saved():
        if not state:return state
        if not is_day and (inp.get('context') or {}).get('kind')=='multi':return await multicity.load(draft_id)
        row=await drafts.get_draft(draft_id)
        return {'request':json.loads(row.request_json),'days_detail':json.loads(row.days_detail_json)}

    runtime=trace.TraceRuntime(trace.TraceConfig(enabled=True,export_enabled=False,directory=directory/'traces',
        project='trip-eval-local',environment='eval',execution_mode='live_model_with_replay' if live else 'replay',data_origin=trace_origin(job['case']['data_origin']),identity_key=b'isolated-eval-local-alias-key-0001'))
    trace._runtime=runtime
    obs=dict(schema_version='trip-eval-v1',case_id=cid,case_version=job['case']['case_version'],input_sha256=job['case']['input_sha256'],
        run_id=job['slot_id'],experiment_id=job['experiment_id'],repetition=job['repetition'],execution_status='error',
        provenance='baseline' if variant=='baseline' else 'injected_failure' if fault else 'no_model' if job['case']['execution_mode']=='no_model' else 'live_model_with_replay' if live else 'replay_model',
        before_state=await saved(),latest_state=None,after_state=None,raw_model=None,final_output=None,model_status='not_called',
        actual_model_calls=0,external_calls_after_cancel=0,recovery_count=0,route_deadline_seconds=110 if is_day else None,usage=None)
    engineering={'model_transport':'disabled','model_substitute_calls':0,'route_replay_edges':[], 'captured_prompts':[], 'actual_live_model_requests':0,
        'fault_kind':fault['kind'] if fault else None,'deadline_scaled_for_test':bool(fault and fault['kind']=='route_timeout')}
    budget=CallBudget(job['live_limits']) if live else None
    live_model=None
    if live:
        if job['live_limits'].get('model') and os.environ.get('LLM_MODEL_NAME')!=job['live_limits']['model']:
            raise ValueError('quoted worker model mismatch')
        from app.services.llm_service import get_llm
        live_model=get_llm()
        engineering['model_transport']='live_direct_deepseek'
    entered=asyncio.Event(); resume=asyncio.Event(); cancelled=False
    check_obj=None; captured=[]; last_projection=None
    original_eval=ticket_schedule.ScheduleCheck.evaluate
    original_load=ticket.load_schedule
    original_sync=ticket_schedule.synchronize_days
    original_projection=multicity.projection
    original_route_context=day_api.build_route_context
    enriching=False
    async def route_context(*args,**kwargs):
        nonlocal enriching
        enriching=True
        try:result=await original_route_context(*args,**kwargs)
        finally:enriching=False
        engineering['route_context_input']=copy.deepcopy(result)
        return result
    def sync(*a,**kw):
        nonlocal last_projection
        result=original_sync(*a,**kw);details,impacts,_=result
        last_projection=[dict(id='draft',days=[d.model_dump(mode='json') if d else None for d in details],windows=[dict(date=i['date'],**i['window']) for i in impacts])]
        return result
    def project(*a,**kw):
        nonlocal last_projection
        result=original_projection(*a,**kw);last_projection=result['cities'];return result
    async def load(*a,**kw):
        nonlocal check_obj
        check_obj=await original_load(*a,**kw);return check_obj
    def evaluate(check,candidate):
        nonlocal last_projection
        last_projection=None
        leg,reasons,conflicts=original_eval(check,candidate);margins=[]
        for city in last_projection or []:
            if check.context.kind=='multi' and city['id'] not in check.affected:continue
            for d in city['days']:
                if not d or d['date'] not in {leg.departure_time[:10],leg.arrival_time[:10]}:continue
                timeline=[t for t in d.get('timeline_schedule',[]) if t['kind']!='free_time']
                if not timeline:continue
                w=next(w for w in city['windows'] if w['date']==d['date'])
                departure=check.context.kind=='draft' and check.query.direction=='inbound' or check.context.kind=='multi' and city['id']==check.edge[0]
                arrival=check.context.kind=='draft' and check.query.direction=='outbound' or check.context.kind=='multi' and city['id']==check.edge[1]
                if departure and d['date']==leg.departure_time[:10]:margins.append(w['end_minutes']-max(t['end_minutes'] for t in timeline))
                if arrival and d['date']==leg.arrival_time[:10]:margins.append(min(t['start_minutes'] for t in timeline)-w['start_minutes'])
        captured.append(dict(candidate_id=candidate.id,eligible=not conflicts,reasons=conflicts,margins=margins if last_projection is not None else None,tight=bool(margins) and 0<=min(margins)<=30))
        return leg,reasons,conflicts

    class ReplayModel:
        async def ainvoke(self,messages):
            nonlocal cancelled
            from .prompt_variants import for_variant
            messages=for_variant(messages,job.get('eval_input_variant','current'))
            trace.record(prompt_alias=trace.alias(json.dumps(message_payload(messages),ensure_ascii=False,sort_keys=True)))
            if cancelled:obs['external_calls_after_cancel']+=1
            engineering['model_substitute_calls']+=1
            obs['actual_model_calls']+=1 # executed model boundary; provenance excludes substitute from live quality
            engineering['captured_prompts'].append([dict(role=m[0],content=m[1]) if isinstance(m,tuple) else dict(role=m.type,content=m.content) for m in messages])
            obs['model_status']='success'
            if fault and fault['kind']=='model_timeout':
                obs['model_status']='timeout';raise ExternalServiceError('llm','eval_injected',FailureKind.TIMEOUT)
            if fault and fault['kind'] in {'cancel','concurrent_change','concurrent_delete_meal'}:
                entered.set()
                try:await resume.wait()
                except asyncio.CancelledError:obs['model_status']='cancelled';cancelled=True;raise
            if fault and 'response' in fault:value=copy.deepcopy(fault['response'])
            elif is_day:
                # A neutral stand-in, not an answer generator. No reference/hint solving.
                value={'attractions_order':[a['name'] for a in inp['day_detail']['attractions']],
                    'meals':day_api._saved_meals(DayDetail.model_validate(inp['day_detail']))}
            else:
                body=json.loads(messages[-1][1] if isinstance(messages[-1],tuple) else messages[-1].content)
                candidates=[ticket.ObservedTicket.model_validate(c) for c in body['candidates']]
                value={'ids':[c.id for c in sorted(candidates,key=lambda c:ticket.rule_key(c,body['query']['priority']))[:3]]}
            obs['raw_model']=copy.deepcopy(value)
            return AIMessage(content=json.dumps(value,ensure_ascii=False))

    class LiveModel:
        async def ainvoke(self,messages):
            if engineering.get('budget_stop') or engineering.get('uncertain_usage'):
                raise BudgetStop('prior request unresolved or budget stopped')
            try:
                from .prompt_variants import for_variant
                messages=for_variant(messages,job.get('eval_input_variant','current'))
                trace.record(prompt_alias=trace.alias(json.dumps(message_payload(messages),ensure_ascii=False,sort_keys=True)))
                receipt=budget.reserve(messages)
            except (BudgetStop,ValueError):
                engineering['budget_stop']=True
                raise
            # Durable reservation precedes the network call, even if this process dies.
            dump(directory/'model-receipts.json',budget.receipts)
            engineering['actual_live_model_requests']+=1
            obs['actual_model_calls']+=1;obs['model_status']='success'
            engineering['captured_prompts'].append([dict(role=m[0],content=m[1]) if isinstance(m,tuple) else dict(role=m.type,content=m.content) for m in messages])
            try:
                response=await live_model.ainvoke(messages)
                text=response.content or ''
                match=re.search(r'\{.*\}',text,re.DOTALL)
                try:obs['raw_model']=json.loads(match.group()) if match else None
                except ValueError:obs['raw_model']=None
                if obs['raw_model'] is None:obs['model_status']='error'
                budget.record(receipt,response)
                return response
            except BudgetStop:
                engineering['budget_stop']=True;raise
            except BaseException as error:
                obs['model_status']='error'
                # Billed status is unknown. Do not enter even a bounded retry.
                engineering['uncertain_usage']=True
                if isinstance(error,asyncio.CancelledError):raise
                budget.stop('model request outcome uncertain; further dispatch forbidden')
            finally:dump(directory/'model-receipts.json',budget.receipts)

    async def route(detail,city,transportation):
        if fault and fault['kind']=='route_timeout':
            entered.set()
            try:await asyncio.Event().wait()
            finally:engineering['route_child_cancelled']=True
        matrix={(e['from'],e['to']):e for e in job['routes']['edges']}
        names=[x['ref_name'] for x in detail.timeline_order if x['kind'] in {'hotel','meal','attraction'}]
        segments=[]
        for a,b in zip(names,names[1:]):
            if a==b:continue
            edge=matrix.get((a,b))
            if edge is None:
                if enriching:engineering.setdefault('input_missing_edges',[]).append([a,b])
                else:engineering['final_missing_route']=[a,b]
                raise ExternalServiceError('amap','eval_missing_frozen_route',FailureKind.UNAVAILABLE)
            engineering['route_replay_edges'].append(edge['edge_id'])
            segments.append(RouteSegment(from_name=a,to_name=b,mode=edge['mode'],duration=f"{edge['duration_minutes']}分钟",distance=f"{edge.get('distance_m',0)}米",is_estimated=False))
        return segments

    async def baseline_ticket(request):
        check=await load(request.context,request.query) if request.context else None
        eligible=[];excluded=[];facts={}
        for c in request.candidates:
            if c.availability in {'unavailable','waitlist'}:continue
            leg,reasons,conflicts=check.evaluate(c) if check else (c.leg(request.query.passengers),['未核对已存安排'],[])
            if conflicts:excluded.append(dict(candidate=c.model_dump(),leg=leg.model_dump(mode='json'),conflicts=conflicts))
            else:eligible.append(c);facts[c.id]=(leg,reasons)
        if check:await check.assert_current()
        selected=sorted(eligible,key=lambda c:ticket.rule_key(c,request.query.priority))[:3]
        recommendations=[]
        for c in selected:
            leg,reasons=facts[c.id]
            notes=['规则基线：仅比较本批可容纳候选，同行总额待核对']
            if c.fare_per_person is None:notes.append('价格未知')
            if c.availability=='unknown':notes.append('余票未知')
            recommendations.append(dict(candidate=c.model_dump(),leg=leg.model_dump(mode='json'),reasons=reasons+notes))
        return dict(ranked_by='rules',recommendations=recommendations,read_count=len(request.candidates),eligible_count=len(eligible),
            message='纯规则基线' if selected else '当前候选均冲突' if excluded else '均无票或候补',schedule_basis=check.basis if check else None,
            checked_schedule=bool(check),fit_count=len(eligible),excluded_count=len(excluded),excluded=excluded)

    @asynccontextmanager
    async def shortened_deadline(seconds):
        engineering['requested_operation_deadline_seconds']=seconds
        async with operation_deadline(.03):yield

    async def run_operation():
        if is_day:
            if variant=='baseline':return copy.deepcopy(inp['day_detail'])
            response=await day_api.ai_rearrange_day(draft_id,inp['day_detail']['day_index'],day_api.AIRearrangeRequest(hint=inp['hint']))
            return response.day_detail.model_dump(mode='json')
        req=ticket.TicketRankingRequest.model_validate({k:inp[k] for k in ('query','candidates','context')})
        return await (baseline_ticket(req) if variant=='baseline' else ticket.rank_tickets(req))

    start=time.monotonic()
    with ExitStack() as stack:
        stack.enter_context(patch.object(ticket,'get_llm',return_value=LiveModel() if live else ReplayModel()))
        stack.enter_context(patch.object(day_api,'get_llm',return_value=LiveModel() if live else ReplayModel()))
        stack.enter_context(patch.object(ticket,'load_schedule',new=load))
        stack.enter_context(patch.object(ticket_schedule.ScheduleCheck,'evaluate',new=evaluate))
        stack.enter_context(patch.object(ticket_schedule,'synchronize_days',new=sync))
        stack.enter_context(patch.object(multicity,'projection',new=project))
        stack.enter_context(patch.object(day_api,'compute_day_route',new=route))
        stack.enter_context(patch.object(day_api,'build_route_context',new=route_context))
        # Freeze business quote timestamp, not operation wall-clock/trace timestamps.
        class Clock(datetime):
            @classmethod
            def now(cls,tz=None):
                value=datetime.fromisoformat(job['case']['clock']);return value.astimezone(tz) if tz else value.replace(tzinfo=None)
        stack.enter_context(patch.object(ticket,'datetime',Clock))
        if fault and fault['kind']=='route_timeout':stack.enter_context(patch.object(day_api,'operation_deadline',new=shortened_deadline))
        task=asyncio.create_task(run_operation())
        try:
            if fault and fault['kind'] in {'cancel','concurrent_change','concurrent_delete_meal'}:
                barrier=asyncio.create_task(entered.wait())
                done,_=await asyncio.wait({task,barrier},timeout=5,return_when=asyncio.FIRST_COMPLETED)
                if not entered.is_set():
                    barrier.cancel();await asyncio.gather(barrier,return_exceptions=True)
                    if task in done:await task
                    raise TimeoutError('fault barrier was not reached')
                if fault['kind']=='cancel':task.cancel()
                elif fault['kind']=='concurrent_change':
                    async def mutate(d,session):d['plan']['budget']=fault['mutation']['value'];return d
                    await multicity.write(draft_id,state['revision'],mutate)
                    obs['latest_state']=await saved();resume.set()
                else:
                    async with database.async_session() as session:
                        row=await session.get(TripDraft,draft_id);days=json.loads(row.days_detail_json);d=days[0]
                        deleted={m['name'] for m in d['meals'] if m.get('preferred_slot',m.get('type'))=='dinner'}
                        d['meals']=[m for m in d['meals'] if m['name'] not in deleted]
                        d['timeline_order']=[x for x in d['timeline_order'] if x.get('ref_name') not in deleted]
                        d['timeline_schedule']=[x for x in d['timeline_schedule'] if x.get('ref_name') not in deleted]
                        row.days_detail_json=json.dumps(days);await session.commit()
                    obs['latest_state']=await saved();resume.set()
            result=await task
            obs.update(final_output=result,execution_status='success',http_status=200)
            if is_day:obs['business_outcome']=(result.get('route_comparison') or {}).get('status','adjusted')
            else:
                from .outcomes import ticket_outcome
                obs['business_outcome']=ticket_outcome(result)
                if variant=='baseline' and result['recommendations']:obs['business_outcome']='recommended'
        except asyncio.CancelledError:
            obs.update(execution_status='cancelled',business_outcome='cancelled',http_status=None)
        except HTTPException as error:
            status='conflict' if error.status_code==409 else 'rejected'
            obs.update(execution_status=status,business_outcome=status,http_status=error.status_code)
        except ExternalServiceError as error:
            status='timeout' if error.kind==FailureKind.TIMEOUT else 'error'
            obs.update(execution_status=status,business_outcome=status,http_status=504 if status=='timeout' else 503)
        except Exception as error:
            obs.update(execution_status='error',business_outcome='error',http_status=500)
            engineering['operation_error_type']=type(error).__name__
            import traceback
            engineering['operation_error_frames']=[dict(file=Path(f.filename).name,line=f.lineno,function=f.name) for f in traceback.extract_tb(error.__traceback__)]
        finally:
            if not task.done():task.cancel();await asyncio.gather(task,return_exceptions=True)
    obs['timings']={'operation_wall_seconds':time.monotonic()-start}
    if fault and fault['kind']=='concurrent_change':
        from app.api.routes.multicity import preview,Change
        from app.models.multicity import MultiTrip
        status=None
        try:await preview(draft_id,Change(plan=MultiTrip.model_validate(state['plan']),revision=state['revision'],ticket_basis=check_obj.basis if check_obj else 'missing_observed_basis'))
        except HTTPException as error:status=error.status_code
        obs['checkpoint_statuses']={'old_recommendation':obs['http_status'],'old_basis_preview':status}
    obs['after_state']=await saved()
    if fault and fault['kind']=='invalid_model_id':
        engineering['injection_exercised']=bool(obs['actual_model_calls'])
    if not is_day:
        observed={x['candidate_id']:x for x in captured}
        for c in inp['candidates']:
            if c['id'] not in observed:
                observed[c['id']]=dict(candidate_id=c['id'],eligible=c['availability'] not in {'unavailable','waitlist'} and not inp['context'],reasons=[],margins=[],tight=False)
        obs['candidate_checks']=list(observed.values());obs['eligible_ids']=[x['candidate_id'] for x in observed.values() if x['eligible']]
    runtime.close(2)
    traces=list((directory/'traces/operations').glob('*.json'))
    if traces:
        obs['trace']=json.loads(traces[0].read_text());obs['trace_id']=obs['trace']['operation_id']
        obs['recovery_count']=sum(s['name']=='saved_schedule_recovery' for s in obs['trace']['spans'])
        if any(s.get('facts',{}).get('preserved_original') for s in obs['trace']['spans']):obs['business_outcome']='preserved_original'
    if live:
        engineering['model_receipts']=budget.receipts
        receipts=[r['usage'] for r in budget.receipts]
        if receipts and all(receipts):obs['usage']={k:sum(r[k] for r in receipts) for k in ('input_tokens','output_tokens','total_tokens')}
        from app.services.llm_service import close_llm
        await close_llm()
    dump(directory/'observation.json',obs);dump(directory/'engineering.json',engineering)
    await database.engine.dispose()


def main():
    directory=Path.cwd().resolve();job=json.loads((directory/'job.json').read_text())
    guard(directory,live=job['variant']=='current_live' and not job['inputs'].get('fault') and job['case']['execution_mode']=='live_model_with_replay')
    try:asyncio.run(execute(job,directory))
    except Exception as error:
        import traceback
        dump(directory/'worker-error.json',{'status':'ERROR','reason':'worker_failed','error_type':type(error).__name__,
            'frames':[dict(file=Path(f.filename).name,line=f.lineno,function=f.name) for f in traceback.extract_tb(error.__traceback__)]})
        raise SystemExit(1) from None


if __name__=='__main__':main()
