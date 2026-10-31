"""Local quality-only preview: no application startup, business database or model clients.

QUALITY_WORKBENCH_ENABLED=1 python -m uvicorn evals.serve_workbench:app --host 127.0.0.1 --port 18027
"""
from fastapi import FastAPI
from app.api.routes.quality import router

app = FastAPI(title='Local quality workbench', docs_url=None, redoc_url=None)
app.include_router(router, prefix='/api')
