"""Pre-call reservation, not a fabricated provider bill. No network or credentials."""
import math
import time
from .contracts import digest

RATES={'model':'deepseek-v4-pro','currency':'USD','checked_on':'2026-10-24',
    'source':'https://api-docs.deepseek.com/quick_start/pricing/',
    'input_miss_peak_per_million':1.32,'input_hit_peak_per_million':.044,'output_peak_per_million':3.96,
    'input_miss_off_peak_per_million':.66,'input_hit_off_peak_per_million':.022,'output_off_peak_per_million':1.98,
    'service_version':'DeepSeek-V4-Pro-0813','cache_assumption':'all cache miss; peak used for reservation'}


def prompt_bound(messages):
    # Provider tokenizer is not installed; this is a conservative byte-based reservation,
    # not reported as measured tokens. Message envelope allowance is explicit.
    return sum(len((m[1] if isinstance(m,tuple) else m.get('content','') if isinstance(m,dict) else m.content).encode('utf-8'))+32 for m in messages)+1024


def estimated_cost(input_tokens,output_tokens,rates=RATES):
    return (input_tokens*rates['input_miss_peak_per_million']+output_tokens*rates['output_peak_per_million'])/1_000_000


class BudgetStop(RuntimeError):pass


def message_payload(messages):
    return [dict(role=m[0],content=m[1]) if isinstance(m,tuple) else
            dict(role=m['role'],content=m['content']) if isinstance(m,dict) else
            dict(role=m.type,content=m.content) for m in messages]


class CallBudget:
    def __init__(self,limits):
        self.limits=limits;self.calls=0;self.tokens=0;self.cost=0.;self.receipts=[];self.stopped=False
        for key in ('max_requests','max_tokens','max_output_tokens'):
            if type(limits[key]) is not int or limits[key]<0:raise ValueError('invalid budget limit')
        if not math.isfinite(limits['max_cost']) or limits['max_cost']<0:raise ValueError('invalid cost limit')
        for key in ('input_miss_peak_per_million','output_peak_per_million'):
            if not math.isfinite(limits['rates'][key]) or limits['rates'][key]<0:raise ValueError('invalid rate')

    def stop(self,reason):
        self.stopped=True
        raise BudgetStop(reason)

    def reserve(self,messages):
        if self.stopped or any(r['usage'] is None for r in self.receipts):
            self.stop('prior request usage unresolved; further dispatch forbidden')
        if self.limits.get('prompt_sha256') and digest(message_payload(messages))!=self.limits['prompt_sha256']:
            self.stop('prompt changed since approved quote')
        inp=prompt_bound(messages);out=self.limits['max_output_tokens'];cost=estimated_cost(inp,out,self.limits['rates'])
        if self.limits.get('input_tokens_per_request') is not None and inp>self.limits['input_tokens_per_request']:
            self.stop('prompt exceeds quoted input reservation')
        if (self.calls+1>self.limits['max_requests'] or self.tokens+inp+out>self.limits['max_tokens'] or self.cost+cost>self.limits['max_cost']+1e-9):
            self.stop('pre-call budget exhausted')
        self.calls+=1;self.tokens+=inp+out;self.cost+=cost
        receipt={'request_index':self.calls,'started_at':time.time(),'prompt_sha256':digest(message_payload(messages)),
                 'input_token_reservation':inp,'output_token_reservation':out,'reserved_cost_upper':cost,'usage':None,'estimated_cost_upper':None}
        self.receipts.append(receipt);return receipt
    def record(self,receipt,response):
        receipt['finished_at']=time.time()
        usage=getattr(response,'usage_metadata',None)
        if usage and all(type(usage.get(k)) is int and usage[k]>=0 for k in ('input_tokens','output_tokens','total_tokens')) and usage['total_tokens']==usage['input_tokens']+usage['output_tokens']:
            receipt['usage']=dict(usage);receipt['estimated_cost_upper']=estimated_cost(usage['input_tokens'],usage['output_tokens'],self.limits['rates'])
            meta=getattr(response,'response_metadata',{}) or {}
            receipt['response_metadata']={k:meta[k] for k in ('model_name','finish_reason') if k in meta}
            token_usage=meta.get('token_usage') or {}
            receipt['provider_cache_tokens']={k:token_usage[k] for k in ('prompt_cache_hit_tokens','prompt_cache_miss_tokens') if type(token_usage.get(k)) is int}
            if self.limits.get('model') == 'deepseek-flash' and meta.get('model_name') not in {
                    'deepseek-flash','DeepSeek-V4.1-Flash-1017','deepseek-v4-flash','deepseek-v4-flash-vision-exp'}:
                self.stop('provider returned an unquoted model; stop further calls')
            if usage['input_tokens']>receipt['input_token_reservation'] or usage['output_tokens']>receipt['output_token_reservation']:
                self.stop('provider usage exceeded reservation; stop further calls')
        else:
            # Request can have been billed even with absent usage. Keep reservation;
            # never turn it into zero and never automatically retry it.
            self.stop('usage unavailable after response; stop further calls')
