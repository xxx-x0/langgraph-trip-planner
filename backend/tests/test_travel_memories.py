"""End-to-end memory API on disposable SQLite/media, with no external services."""
import asyncio
import copy
import hashlib
import io
import json
import stat
import time
import zipfile
from uuid import uuid4

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI
from PIL import Image
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.database import Base
from app.models.db_models import TripDraft, TripRecord, UserPreferenceRecord
from app.models.travel_memory import TravelMemoryRow
from app.api.routes.travel_memories import router
from app.services import memory_backup as backup, memory_media as media, travel_memories as svc

pytestmark = pytest.mark.asyncio
ROOT = '/api/travel-records'

@pytest_asyncio.fixture
async def client(tmp_path, monkeypatch):
    engine = create_async_engine(f'sqlite+aiosqlite:///{tmp_path / "memory.db"}')
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(svc, 'async_session', sessions)
    monkeypatch.setattr(backup, 'async_session', sessions)
    monkeypatch.setenv('TRAVEL_MEMORY_STORAGE_DIR', str(tmp_path / 'media'))
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    app = FastAPI(); app.include_router(router, prefix='/api')
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app, raise_app_exceptions=False), base_url='http://test') as c:
        yield c
    await engine.dispose()

def body(**overrides):
    return {**dict(id=uuid4().hex, title='杭州的周末', note='湖边散步', visits=[dict(id='visit-1', city='杭州', country='中国', region='浙江', latitude=30.2741, longitude=120.1551)]), **overrides}

async def create(client, value=None):
    r = await client.post(ROOT, json=value or body())
    assert r.status_code == 200, r.text
    return r.json()

def edit(record, **changes):
    d = copy.deepcopy(record['document'])
    for key in ('source', 'deleted'): d.pop(key)
    d['photos'] = [{k: p[k] for k in ('id','caption','moment_id','deleted','focal_x','focal_y')} for p in d['photos']]
    d.update(revision=record['revision'], operation_id=uuid4().hex, **changes)
    return d

async def update(client, record, **changes):
    r = await client.put(ROOT + '/' + record['id'], json=edit(record, **changes))
    assert r.status_code == 200, r.text
    return r.json()

def picture(color='blue', fmt='JPEG', orientation=None):
    image = Image.new('RGB', (100,60), color); output = io.BytesIO(); kwargs = {}
    if orientation:
        exif = Image.Exif(); exif[274] = orientation; exif[270] = 'original metadata'; kwargs['exif'] = exif
    image.save(output, fmt, **kwargs)
    return output.getvalue()

async def upload(client, record, data=None, photo_id=None):
    r = await client.post(f'{ROOT}/{record["id"]}/photos', data={'revision':record['revision'],'photo_id':photo_id or uuid4().hex}, files={'file':('旅途.jpg',data or picture(),'image/jpeg')})
    assert r.status_code == 200, r.text
    return r.json()

async def preview(client, data):
    return await client.post(ROOT+'/restore/preview', files={'file':('memories.zip',data,'application/zip')})

async def confirm(client, result, policy='copy'):
    return await client.post(ROOT+'/restore/confirm', json={'token':result['token'],'conflicts':policy})

def rewrite_zip(data, mutate):
    with zipfile.ZipFile(io.BytesIO(data)) as z: files = {n:z.read(n) for n in z.namelist()}
    mutate(files); output = io.BytesIO()
    with zipfile.ZipFile(output,'w') as z:
        for n,v in files.items(): z.writestr(n,v)
    return output.getvalue()

async def test_unknown_dates_repeated_visits_and_idempotent_create(client):
    value=body(title=''); value['visits'].append({**value['visits'][0],'id':'visit-2'})
    first=await create(client,value)
    assert first['document']['when']==dict(precision='unknown',start='',end='')
    assert first['document']['title']=='杭州的记忆' and len(first['document']['visits'])==2
    assert await create(client,value)==first
    value['note']='different retry'
    assert (await client.post(ROOT,json=value)).status_code==409
    assert len((await client.get(ROOT)).json())==1

@pytest.mark.parametrize('when,valid',[
    ({'precision':'year','start':'2020'},True),
    ({'precision':'month','start':'2020-02','end':'2021-01'},True),
    ({'precision':'day','start':'2020-02-29'},True),
    ({'precision':'unknown','start':'2020'},False),
    ({'precision':'day','start':'2021-02-29'},False),
    ({'precision':'month','start':'2020-13'},False),
    ({'precision':'year','start':'2999'},False),
    ({'precision':'year','start':'1899'},False),
    ({'precision':'day','start':'2020-01-02','end':'2020-01-01'},False),
    ({'precision':'year','start':''},False),
])
async def test_date_precision_and_past_only(client,when,valid):
    r=await client.post(ROOT,json=body(when=when))
    assert r.status_code==(200 if valid else 422),r.text
    if valid: assert r.json()['document']['when']['start']==when['start']

async def test_validation_preserves_records(client):
    record=await create(client); value=edit(record); value['visits'][0]['longitude']=None
    assert (await client.put(ROOT+'/'+record['id'],json=value)).status_code==422
    value=edit(record,moments=[{'id':'m1','visit_id':'missing'}])
    assert (await client.put(ROOT+'/'+record['id'],json=value)).status_code==422
    assert (await client.get(ROOT+'/'+record['id'])).json()==record

async def test_edit_cas_retry_and_concurrent_writes(client):
    record=await create(client); value=edit(record,note='本次编辑')
    r=await client.put(ROOT+'/'+record['id'],json=value)
    assert r.status_code==200
    assert (await client.put(ROOT+'/'+record['id'],json=value)).json()==r.json()
    assert (await client.put(ROOT+'/'+record['id'],json=edit(record,note='late'))).status_code==409
    latest=r.json()
    replies=await asyncio.gather(*(client.put(ROOT+'/'+record['id'],json=edit(latest,note=str(i))) for i in range(2)))
    assert sorted(r.status_code for r in replies)==[200,409]
    assert (await client.get(ROOT+'/'+record['id'])).json()['revision']==3

async def test_original_exif_thumbnail_retry_and_soft_deletion(client):
    first=await create(client); raw=picture(orientation=6); photo_id=uuid4().hex
    record=await upload(client,first,raw,photo_id)
    assert await upload(client,first,raw,photo_id)==record
    photo=record['document']['photos'][0]
    assert (photo['width'],photo['height'])==(60,100)
    assert (await client.get(f'{ROOT}/{record["id"]}/photos/{photo_id}')).content==raw
    thumb=await client.get(f'{ROOT}/{record["id"]}/photos/{photo_id}?preview=true')
    image=Image.open(io.BytesIO(thumb.content)); assert image.size==(60,100) and not image.getexif()
    record=await update(client,record,moments=[{'id':'moment','text':'<script>literal memory</script>'}])
    value=edit(record); value['photos'][0].update(caption='湖边的风',moment_id='moment',focal_x=17,focal_y=81)
    record=(await client.put(ROOT+'/'+record['id'],json=value)).json()
    value=edit(record); value['photos'][0]['deleted']=True; value['cover_photo_id']=None
    record=(await client.put(ROOT+'/'+record['id'],json=value)).json()
    assert record['document']['photos'][0]['sha256']==hashlib.sha256(raw).hexdigest()
    assert (await client.get(f'{ROOT}/{record["id"]}/photos/{photo_id}')).content==raw
    value=edit(record); value['photos'][0]['deleted']=False; value['cover_photo_id']=photo_id
    record=(await client.put(ROOT+'/'+record['id'],json=value)).json()
    assert record['document']['photos'][0]['caption']=='湖边的风'
    trashed=(await client.patch(f'{ROOT}/{record["id"]}/trash',json={'revision':record['revision'],'deleted':True})).json()
    assert (await client.put(ROOT+'/'+record['id'],json=edit(trashed))).status_code==409
    restored=(await client.patch(f'{ROOT}/{record["id"]}/trash',json={'revision':trashed['revision'],'deleted':False})).json()
    assert restored['document']==record['document']

async def test_album_order_and_metadata_cannot_drop_originals(client):
    record=await upload(client,await create(client)); record=await upload(client,record,picture('red'))
    value=edit(record); value['photos'].reverse(); value['cover_photo_id']=value['photos'][0]['id']
    r=await client.put(ROOT+'/'+record['id'],json=value); assert r.status_code==200
    record=r.json(); assert record['document']['photos'][0]['sha256']==hashlib.sha256(picture('red')).hexdigest()
    value=edit(record); value['photos'].pop()
    assert (await client.put(ROOT+'/'+record['id'],json=value)).status_code==409
    value=edit(record); value['photos'][0]['sha256']='0'*64
    assert (await client.put(ROOT+'/'+record['id'],json=value)).status_code==422

@pytest.mark.parametrize('data',[b'<svg onload=alert(1)>',b'not a photo',picture(fmt='GIF')])
async def test_invalid_photo_never_changes_record(client,data):
    record=await create(client)
    r=await client.post(f'{ROOT}/{record["id"]}/photos',data={'revision':1,'photo_id':uuid4().hex},files={'file':('fake.jpg',data,'image/jpeg')})
    assert r.status_code==415
    assert (await client.get(ROOT+'/'+record['id'])).json()==record

async def test_media_failure_preserves_last_success(client,monkeypatch):
    record=await create(client)
    def unavailable(*_): raise OSError('injected disk failure')
    monkeypatch.setattr(media,'store_photo',unavailable)
    r=await client.post(f'{ROOT}/{record["id"]}/photos',data={'revision':1,'photo_id':uuid4().hex},files={'file':('test.jpg',picture(),'image/jpeg')})
    assert r.status_code==500
    assert (await client.get(ROOT+'/'+record['id'])).json()==record

async def test_backup_roundtrip_including_trash_and_missing_original(client):
    record=await upload(client,await create(client),picture(orientation=6))
    record=await update(client,record,when={'precision':'month','start':'2020-05'},moments=[{'id':'removed','text':'still kept','deleted':True}])
    record=(await client.patch(f'{ROOT}/{record["id"]}/trash',json={'revision':record['revision'],'deleted':True})).json()
    archive=(await client.get(ROOT+'/backup')).content; original=record['document']['photos'][0]
    media.blob_path(original['sha256']).unlink()
    assert (await client.get(ROOT+'/backup')).status_code==409
    async with svc.async_session() as session:
        await session.execute(delete(TravelMemoryRow)); await session.commit()
    planned=(await preview(client,archive)).json()
    assert planned['counts']['new']==1 and planned['photo_files_to_restore']==1
    result=await confirm(client,planned)
    assert result.json()=={'added':1,'copied':0,'skipped':0}
    assert (await confirm(client,planned)).json()==result.json()
    restored=(await client.get(ROOT+'/'+record['id'])).json()
    assert restored['document']==record['document']
    assert media.checked_original(original['sha256'])==picture(orientation=6)
    second=(await preview(client,archive)).json()
    assert second['counts']['identical']==1 and (await confirm(client,second)).json()['skipped']==1

async def test_conflict_copy_skip_repeat_and_receipt(client):
    record=await create(client); archive=(await client.get(ROOT+'/backup')).content
    changed=await update(client,record,note='新的回忆'); planned=(await preview(client,archive)).json()
    assert planned['counts']['conflict']==1
    assert (await confirm(client,planned,'skip')).json()['skipped']==1
    assert (await confirm(client,planned,'copy')).status_code==409
    planned=(await preview(client,archive)).json()
    assert (await confirm(client,planned)).json()['copied']==1
    assert (await client.get(ROOT+'/'+record['id'])).json()==changed
    again=(await preview(client,archive)).json()
    assert again['counts']['already_restored']==1 and (await confirm(client,again)).json()['skipped']==1
    assert len((await client.get(ROOT)).json())==2

async def test_stale_and_expired_restore_preview(client):
    record=await create(client); archive=(await client.get(ROOT+'/backup')).content
    planned=(await preview(client,archive)).json(); await update(client,record,note='预览期间修改')
    assert (await confirm(client,planned,'skip')).status_code==409
    planned=(await preview(client,archive)).json(); path=backup.work_dir()/(planned['token']+'.json')
    meta=json.loads(path.read_text()); meta['created']=time.time()-3601; path.write_text(json.dumps(meta))
    assert (await confirm(client,planned)).status_code==409

@pytest.mark.parametrize('damage',['traversal','missing','checksum','version','duplicate','link'])
async def test_bad_backup_is_rejected_without_writes(client,damage):
    record=await upload(client,await create(client)); archive=(await client.get(ROOT+'/backup')).content
    def mutate(files):
        photo=next(n for n in files if n.startswith('media/'))
        if damage=='traversal': files['../escape']=b'bad'
        elif damage=='missing': files.pop(photo)
        elif damage=='checksum': files[photo]=picture('red')
        elif damage=='version':
            doc=json.loads(files['manifest.json']); doc['version']=999; files['manifest.json']=json.dumps(doc).encode()
    bad=rewrite_zip(archive,mutate)
    if damage in ('duplicate','link'):
        output=io.BytesIO(bad)
        with zipfile.ZipFile(output,'a') as z:
            if damage=='duplicate':
                with pytest.warns(UserWarning): z.writestr('manifest.json',b'{}')
            else:
                info=zipfile.ZipInfo('media/'+'a'*64); info.create_system=3; info.external_attr=(stat.S_IFLNK|0o777)<<16; z.writestr(info,b'/etc/passwd')
        bad=output.getvalue()
    r=await preview(client,bad); assert r.status_code==422,r.text
    assert (await client.get(ROOT+'/'+record['id'])).json()==record
    assert not list(backup.work_dir().glob('*.zip'))

async def test_corrupt_original_can_be_repaired_without_changing_record(client):
    record=await upload(client,await create(client)); archive=(await client.get(ROOT+'/backup')).content
    path=media.blob_path(record['document']['photos'][0]['sha256']); path.write_bytes(b'broken')
    planned=(await preview(client,archive)).json()
    assert planned['counts']['identical']==1 and planned['photo_files_to_restore']==1
    assert (await confirm(client,planned)).status_code==200
    assert (await client.get(ROOT+'/'+record['id'])).json()==record and path.read_bytes()==picture()

async def test_import_requires_confirmation_preserves_plan_and_preferences(client):
    multi={'kind':'multi_city_v1','status':'saved','plan':{'title':'苏杭旧计划','start_date':'2020-05-01','end_date':'2020-05-05','stops':[dict(id='su',city={'name':'苏州'},start_date='2020-05-01',end_date='2020-05-03'),dict(id='hz',city={'name':'杭州'},start_date='2020-05-03',end_date='2020-05-05')]}}
    async with svc.async_session() as session:
        single=TripRecord(title='未来北京计划',city='北京市',start_date='2099-01-01',end_date='2099-01-02',travel_days=2,plan_data='{"unchanged":true}')
        pref=UserPreferenceRecord(user_id='default',source='explicit',preference_data='{"keep":"unchanged"}')
        draft=TripDraft(id='mc-memory-test',status='multi_saved',request_json=json.dumps(multi),selected_attractions_json='[]',macro_plan_json='{}',clusters_data_json='{}',hotels_by_day_json='{}',dining_pool_json='[]')
        session.add_all([single,pref,draft]); await session.commit(); single_id=single.id; original=draft.request_json
    sources=(await client.get(ROOT+'/sources')).json()
    assert {i['kind'] for i in sources['items']}=={'single','multi'}
    single=(await client.get(f'{ROOT}/sources/single/{single_id}')).json()
    assert single['visits'][0]['when']['precision']=='unknown' and single['visits'][0]['latitude'] is not None
    source=(await client.get(ROOT+'/sources/multi/mc-memory-test')).json()
    ref={k:source[k] for k in ('kind','id','title','basis')}
    visits=[{k:v for k,v in source['visits'][0].items() if not k.startswith('planned_')}]
    value=body(source=ref,confirmed_visit_ids=[],visits=visits)
    assert (await client.post(ROOT,json=value)).status_code==422
    value['confirmed_visit_ids']=['su']; record=await create(client,value)
    assert [v['city'] for v in record['document']['visits']]==['苏州'] and record['document']['source']==ref
    async with svc.async_session() as session:
        assert (await session.get(TripDraft,'mc-memory-test')).request_json==original
        assert (await session.get(TripRecord,single_id)).plan_data=='{"unchanged":true}'
        prefs=(await session.execute(select(UserPreferenceRecord))).scalars().all()
        assert len(prefs)==1 and prefs[0].preference_data=='{"keep":"unchanged"}'
        row=await session.get(TripDraft,'mc-memory-test'); data=json.loads(row.request_json); data['plan']['title']='changed'; row.request_json=json.dumps(data); await session.commit()
    value['id']=uuid4().hex
    assert (await client.post(ROOT,json=value)).status_code==409

async def test_upload_and_archive_size_limits_leave_last_save(client, monkeypatch):
    record = await create(client)
    monkeypatch.setattr(media, 'MAX_PHOTO_BYTES', 100)
    result = await client.post(f'{ROOT}/{record["id"]}/photos', data={'revision': 1, 'photo_id': uuid4().hex}, files={'file': ('large.jpg', picture(), 'image/jpeg')})
    assert result.status_code == 413
    monkeypatch.setattr(backup, 'MAX_BACKUP_BYTES', 128)
    result = await preview(client, b'x' * 129)
    assert result.status_code == 413 and not list(backup.work_dir().glob('*.zip'))
    assert (await client.get(ROOT + '/' + record['id'])).json() == record

async def test_offline_city_search_disambiguates_regions_and_uses_verified_aliases(client):
    for query, label, region in [('foshan', '佛山', '广东'), ('青岛', '青岛', '山东'), ('tianjin', '天津', '天津'), ('丽江', '丽江', '云南')]:
        rows = (await client.get(ROOT + '/cities', params={'q': query})).json()
        assert any(row['city'] == label and row['region'] == region and row['latitude'] is not None for row in rows)
    rows = (await client.get(ROOT + '/cities', params={'q': 'suzhou'})).json()
    assert any(row['city'] == '苏州' and row['region'] == '江苏' for row in rows)
    assert any(row['city'] == '宿州' and row['region'] == '安徽' for row in rows)
    rows = (await client.get(ROOT + '/cities', params={'q': '巴黎'})).json()
    assert any(row['city'] == 'Paris' and row['country'] == '法国' for row in rows)
