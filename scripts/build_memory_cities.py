"""Build offline city search from a downloaded GeoNames cities15000 snapshot.

Run from repository root: python3 scripts/build_memory_cities.py DATA_DIR
DATA_DIR contains cities15000.zip, countryInfo.txt, admin1CodesASCII.txt,
and CN-alternates.zip (from dump/alternatenames/CN.zip).
Coordinates retain WGS84. Labels/aliases are a convenience, not boundaries.
"""
import hashlib
import json
import re
import subprocess
import sys
import unicodedata
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
source = Path(sys.argv[1])
out = ROOT / 'backend/app/data'
# The original 14 reference cities remain stable; do not duplicate their aliases.
core = json.loads((out / 'memory_cities_core.json').read_text())
country_rows = [s.split('\t') for s in (source / 'countryInfo.txt').read_text().splitlines() if s and not s.startswith('#')]
countries = json.loads(subprocess.check_output(['node', '-e', 'const a=JSON.parse(process.argv[1]);const d=new Intl.DisplayNames(["zh-Hans"],{type:"region"});process.stdout.write(JSON.stringify(Object.fromEntries(a.map(k=>[k,d.of(k)]))))', json.dumps([r[0] for r in country_rows])]))
admin = {r[0]:r[1] for r in (line.split('\t') for line in (source / 'admin1CodesASCII.txt').read_text().splitlines())}
cn_regions = dict(zip('01 02 03 04 05 06 07 08 09 10 11 12 13 14 15 16 18 19 20 21 22 23 24 25 26 28 29 30 31 32 33'.split(), '安徽 浙江 江西 江苏 吉林 青海 福建 黑龙江 河南 河北 湖南 湖北 新疆 西藏 甘肃 广西 贵州 辽宁 内蒙古 宁夏 北京 上海 山西 山东 陕西 天津 云南 广东 海南 四川 重庆'.split()))
with zipfile.ZipFile(source / 'cities15000.zip') as z:
    rows = [line.split('\t') for line in z.read('cities15000.txt').decode().splitlines()]
# All source Chinese places, global cities >=100k, and national capitals.
rows = sorted((r for r in rows if r[8] in ('CN','HK','MO','TW') or int(r[14] or 0)>=100000 or r[7]=='PPLC'), key=lambda r:-int(r[14] or 0))
normalize = lambda s: re.sub('[^a-z0-9]', '', unicodedata.normalize('NFKD', s).encode('ascii','ignore').decode().lower())
zh = {}
with zipfile.ZipFile(source / 'CN-alternates.zip') as z:
    for line in z.open('CN.txt'):
        v = line.decode().rstrip('\n').split('\t')
        if v[2] not in ('zh','zh-CN','zh-Hans') or v[6]=='1' or v[7]=='1':
            continue
        score = (v[2] in ('zh-CN','zh-Hans'), v[4]=='1', not v[3].endswith('市'))
        if v[1] not in zh or score > zh[v[1]][0]: zh[v[1]]=(score,v[3])
entries = list(core)
for r in rows:
    aliases = r[3].split(',')
    lat, lon = float(r[4]), float(r[5])
    if any(abs(c['latitude']-lat)<.35 and abs(c['longitude']-lon)<.35 and normalize(c['search'])==normalize(r[2]) for c in core):
        continue
    han = [s for s in aliases if re.fullmatch(r'[\u4e00-\u9fff]{2,12}',s)]
    # Chinese labels use language-tagged, non-historic aliases; other labels retain source names.
    # All Han aliases remain searchable; never infer a display language from script alone.
    label = zh.get(r[0], (None, r[1]))[1].removesuffix('市') if r[8]=='CN' else r[1]
    region = cn_regions.get(r[10], '') if r[8]=='CN' else admin.get(r[8]+'.'+r[10], '')
    entries.append(dict(city=label[:100],region=region[:100],country=countries.get(r[8],r[8]),latitude=lat,longitude=lon,search=' '.join(dict.fromkeys([r[1],r[2],*han,normalize(r[2])]))))
(out / 'memory_cities.json').write_text(json.dumps(entries,ensure_ascii=False,separators=(',',':'))+'\n')
metadata = dict(source='https://download.geonames.org/export/dump/',license='https://creativecommons.org/licenses/by/4.0/',selection='All CN/HK/MO/TW entries in cities15000; other places population >=100000 or PPLC; 14 finn-digital reference cities override nearby matches.',count=len(entries),files={n:hashlib.sha256((source/n).read_bytes()).hexdigest() for n in ('cities15000.zip','countryInfo.txt','admin1CodesASCII.txt','CN-alternates.zip')})
(out/'memory_cities_source.json').write_text(json.dumps(metadata,ensure_ascii=False,indent=2)+'\n')
print(f'Wrote {len(entries)} offline cities')
