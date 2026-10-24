"""Replay frozen P03 facts offline; no fresh provider or human outcome claim."""
import json,argparse
from pathlib import Path
from app.agents.langgraph_agent.nodes.food import _parse_amap_poi_list,_poi_to_dining_candidate
from app.models.schemas import DiningCandidate,DiningCategory,Attraction
from app.services.recommendations import explain_dining,dining_for_slot

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source',type=Path)
    parser.add_argument('output',type=Path)
    args=parser.parse_args()
    if args.source.resolve()==args.output.resolve() or args.output.exists():
        parser.error('Choose a fresh output file; never overwrite input or prior evidence')
    rows=json.loads(args.source.read_text());result=[]
    for city,lon,lat in [('苏州',120.629,31.324),('杭州',120.149,30.243)]:
        cs=[]
        for row in rows:
            if row['label'].startswith(city+'-restaurant-') and row['label'].endswith('-mcp'):
                p=_parse_amap_poi_list(row['response'])[0]
                c=DiningCandidate.model_validate(_poi_to_dining_candidate(p,DiningCategory.MAIN,'nearby'))
                c.recommendation['queried_at']=row['queried_at'];cs.append(c)
        attrs=[Attraction(name='本次游玩区域',address='',description='',location={'longitude':lon,'latitude':lat},visit_duration=120)]
        for label,intent in [('solo',{'companion_count':1}),('budget',{'companion_count':2,'meal_budget_per_person':50}),('family',{'companion_count':3,'children':True,'dietary_requirements':'不吃辣'}),('dedicated',{'companion_count':1,'dining_style':'dedicated','food_preference':'苏帮菜' if city=='苏州' else '杭帮菜'})]:
            explain_dining(cs,attrs,intent)
            ranked=dining_for_slot(cs,'lunch',intent)
            result.append({'city':city,'scenario':label,'source':'2026-10-15 P03 captured MCP details (replay)',
              'candidates':[{'name':c.name,'poi_id':c.poi_id,'avg_cost':c.avg_cost,'recommendation':c.recommendation,
               'screening_result':'候选比较，不是用户采纳' if i<3 else '排序在备选之后；不是实际体验拒绝'} for i,c in enumerate(ranked)],
              'human_adoption_reason':None,'actual_dining_experience':None})
    args.output.write_text(json.dumps(result,ensure_ascii=False,indent=2))
    count=len({(row['city'],c.get('poi_id') or c['name']) for row in result for c in row['candidates']})
    print(f'{count} distinct restaurant facts, {len(result)} scenario comparisons; historical replay, human outcomes unmeasured')

if __name__=='__main__':
    main()
