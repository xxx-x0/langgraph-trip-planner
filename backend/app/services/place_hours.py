"""Conservative checks against saved opening text, never a live opening guarantee."""
from datetime import date
import re

_TIME = r'(?:[01]?\d|2[0-3]):[0-5]\d'
_RANGE = re.compile(r'('+_TIME+r')\s*[-–—~至]\s*((?:'+_TIME+r')|24:00)')
_MONTH = re.compile(r'(\d{1,2})(?:月)?\s*[-–—~至]\s*(\d{1,2})月')
_ENTRY = re.compile(r'(?:最晚(?:进入|入场|入园)(?:时间)?|停止(?:入场|入园))(?:为)?\s*[:：]?\s*('+_TIME+r')|('+_TIME+r')\s*(?:止入|停止入场|停止入园)')


def _minute(text):
    h,m=map(int,text.split(':'));return h*60+m


def resolve_hours(text, on_date):
    """Support explicit daily intervals/month ranges; abstain on calendar exceptions."""
    unknown=dict(status='unknown',windows=[],last_entry=None)
    if not text:return unknown
    try:month=date.fromisoformat(on_date).month
    except (ValueError,TypeError):return unknown
    if any(w in text for w in ['暂停营业','永久关闭','已歇业']):
        return dict(status='closed',windows=[],last_entry=None)
    clean=text.replace('周一至周日','').replace('星期一至星期日','')
    if re.search(r'周[一二三四五六日天末]|星期|工作日|节假日|农历|春节|法定|例外|除外|另行|夏令|冬令|淡季|旺季|\d月\d{1,2}日|\d{4}[-/年]\d{1,2}[-/月]|次日',clean):
        return unknown
    if clean.strip() in {'24小时','24小时营业','全天营业','00:00-24:00'}:
        return dict(status='known',windows=[(0,1440)],last_entry=None)
    markers=list(_MONTH.finditer(clean));rules=[]
    if '月' in _MONTH.sub('',clean):return unknown
    if markers:
        pending=set()
        for index,marker in enumerate(markers):
            a,b=map(int,marker.groups())
            if not 1<=a<=12 or not 1<=b<=12:return unknown
            pending.update(range(a,b+1) if a<=b else list(range(a,13))+list(range(1,b+1)))
            chunk=clean[marker.end():markers[index+1].start() if index+1<len(markers) else len(clean)]
            if _RANGE.search(chunk):rules.append((set(pending),chunk));pending.clear()
        if pending:return unknown
        selected=[chunk for months,chunk in rules if month in months]
        if len(selected)!=1:return unknown
        body=selected[0]
    else:body=clean
    windows=[]
    for a,b in _RANGE.findall(body):
        lo,hi=_minute(a),_minute(b)
        if hi<=lo:
            if markers:return unknown
            if hi>0:windows.append((0,hi))
            hi+=1440
        windows.append((lo,hi))
    entries={_minute(a or b) for a,b in _ENTRY.findall(body)}
    if not windows or len(entries)>1:return unknown
    deadline=next(iter(entries),None)
    if deadline is not None and not any(a<=deadline<=b for a,b in windows):return unknown
    return dict(status='known',windows=windows,last_entry=deadline)


def place_hours_report(detail):
    """Unknown hours are disclosed; explicit contradictions block a new save."""
    violations=[];unknown=[]
    for kind,places in [('attraction',detail.attractions),('meal',detail.meals)]:
        for place in places:
            rule=resolve_hours(place.open_hours,detail.date)
            rows=[r for r in detail.timeline_schedule if r.get('kind')==kind and r.get('ref_name')==place.name]
            if rule['status']=='closed':
                violations.append(place.name+'已被来源标为暂停或停止营业');continue
            if rule['status']=='unknown':
                unknown.append(place.name+'的开放日期、营业或最晚入场规则尚未核实');continue
            if len(rows)!=1:
                violations.append(place.name+'缺少唯一的活动时间安排');continue
            start,end=rows[0]['start_minutes'],rows[0]['end_minutes']
            if not any(a<=start<=end<=b for a,b in rule['windows']):
                violations.append(place.name+'不在已知开放时间内')
            if rule['last_entry'] is not None and start>rule['last_entry']:
                violations.append(place.name+'超过已知最晚入场时间')
    return dict(violations=list(dict.fromkeys(violations)),unknown=list(dict.fromkeys(unknown)))
