"""Local fault demo: simulated services, real HTTP/SSE and isolated SQLite."""
import json
import runpy
from pathlib import Path
from fastapi.responses import JSONResponse

fixture = runpy.run_path(str(Path(__file__).with_name('ltp3_demo.py')))
app = fixture['app']
STATE_DIR = fixture['STATE_DIR']
pipeline = fixture['pipeline']
routes = fixture['trip_draft']
from app.services.external_calls import ExternalServiceError, FailureKind

counts = {'model_calls':0, 'dropped_complete':0}
original_synthesizer = pipeline._run_global_synthesizer
original_narrative = routes.write_day_narrative_llm


def save_counts():
    (STATE_DIR / 'recovery-counts.json').write_text(json.dumps(counts, indent=2))


async def simulated_model(*args, **kwargs):
    counts['model_calls'] += 1
    save_counts()
    flag = STATE_DIR / 'fail-next-model'
    if flag.exists():
        flag.unlink()
        raise ExternalServiceError('llm', 'generate', FailureKind.TIMEOUT)
    return await original_synthesizer(*args, **kwargs)


async def simulated_narrative(*args, **kwargs):
    flag = STATE_DIR / 'fail-next-narrative'
    if flag.exists():
        flag.unlink()
        raise ExternalServiceError('llm', 'generate', FailureKind.TIMEOUT)
    return await original_narrative(*args, **kwargs)


pipeline._run_global_synthesizer = simulated_model
routes.write_day_narrative_llm = simulated_narrative


@app.exception_handler(ExternalServiceError)
async def failed_service(request, error):
    return JSONResponse(status_code=504, content={'detail':str(error),'step':error.operation})


@app.middleware('http')
async def interrupt_after_save(request, call_next):
    response = await call_next(request)
    flag = STATE_DIR / 'drop-next-finalize-complete'
    if not request.url.path.endswith('/finalize') or not flag.exists():
        return response
    flag.unlink()
    original = response.body_iterator
    async def dropped():
        async for chunk in original:
            text = chunk.decode() if isinstance(chunk, bytes) else chunk
            if '"type": "complete"' in text:
                counts['dropped_complete'] += 1
                save_counts()
                return
            yield chunk
    response.body_iterator = dropped()
    return response


if __name__ == '__main__':
    import uvicorn
    print(f'Recovery demo directory: {STATE_DIR}', flush=True)
    print('Use frontend port 5176 against this simulated backend on 18002.', flush=True)
    uvicorn.run(app, host='127.0.0.1', port=18002)
