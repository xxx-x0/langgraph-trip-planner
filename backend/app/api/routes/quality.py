"""Opt-in read-only quality API. Published evidence only; no business DB access."""
import hashlib
import json

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from ...services import quality_reports as quality

router = APIRouter(prefix='/quality', tags=['quality'])


def loaded():
    if not quality.enabled():
        raise HTTPException(403, '质量工作台已关闭')
    return quality.snapshots()


def experiment(identity):
    records, invalid = loaded()
    found = next((r for r in records if r['experiment_id'] == identity), None)
    if not found:
        raise HTTPException(404, '实验不存在或报告不可读取')
    return found


def filters(request):
    allowed = {'variant', 'target', 'split', 'data_origin', 'provenance', 'operation_status', 'business_outcome', 'category', 'q', 'since', 'until'}
    values = {k: v for k, v in request.query_params.items() if k in allowed and v}
    if request.query_params.get('findings') == 'true':
        values['findings'] = True
    return values


def metadata(record):
    return {k: v for k, v in record.items() if k != 'runs'}


@router.get('/status')
def status():
    if not quality.enabled():
        return {'enabled':False, 'state':'disabled', 'cloud_status':'not_checked', 'snapshot_at':None}
    records, invalid = quality.snapshots()
    return dict(enabled=True, state='ready' if records else 'invalid' if invalid else 'empty',
        environment='local_readonly', cloud_status='not_exported', cloud_checked=False,
        snapshot_at=max((r['published_at'] for r in records), default=None),
        invalid_reports=invalid, experiments=len(records), categories=quality.CATEGORIES,
        message='本地冻结报告；未查询云端连接状态，本批次未上传 LangSmith')


@router.get('/experiments')
def experiments():
    records, invalid = loaded()
    return dict(items=[metadata(r) | {'variants':[dict(variant=v, summary=quality.summary([row for row in r['runs'] if row['variant']==v])) for v in sorted({row['variant'] for row in r['runs']})]} for r in records], invalid_reports=invalid)


@router.get('/experiments/compare')
def compare(request: Request, left: str, right: str, left_variant: str='baseline', right_variant: str='current_live'):
    a,b=experiment(left),experiment(right)
    for record, variant in [(a,left_variant),(b,right_variant)]:
        if variant not in {r['variant'] for r in record['runs']}:
            raise HTTPException(422, '未知比较方案')
    return quality.compare(a,b,left_variant,right_variant,filters(request))


@router.get('/experiments/{identity}/export')
def export_experiment(identity: str):
    record = experiment(identity)
    return JSONResponse(record, headers={'Content-Disposition':f'attachment; filename="{record["experiment_id"]}-diagnostic.json"','Cache-Control':'no-store'})


@router.get('/runs')
def runs(request: Request, experiment_id: str, cursor: str | None=None, limit: int=Query(20,ge=1,le=100)):
    record = experiment(experiment_id)
    selected = filters(request)
    rows = quality.select(record, selected)
    fingerprint = hashlib.sha256(json.dumps([record['published_at'], selected, limit],sort_keys=True).encode()).hexdigest()[:16]
    offset = 0
    if cursor:
        try:
            key, pos = cursor.split(':')
            offset = int(pos)
            if key != fingerprint or offset<0 or offset>len(rows):
                raise ValueError()
        except ValueError:
            raise HTTPException(422, '分页已过期，请从第一页刷新')
    next_offset = offset+limit
    return dict(items=[quality.row_public(r) for r in rows[offset:next_offset]], total=len(rows), complete=True,
        next_cursor=f'{fingerprint}:{next_offset}' if next_offset<len(rows) else None,
        summary=quality.summary(rows), snapshot_at=record['published_at'], experiment=metadata(record))


@router.get('/runs/{run_id}')
def run(run_id: str, experiment_id: str, download: bool=False):
    record = experiment(experiment_id)
    row = next((r for r in record['runs'] if r['run_id']==run_id),None)
    if row is None:
        raise HTTPException(404, '运行记录不存在')
    payload = {**row, 'experiment':metadata(record)}
    if download:
        return JSONResponse(payload, headers={'Content-Disposition':f'attachment; filename="{row["run_id"]}-diagnostic.json"','Cache-Control':'no-store'})
    return payload
