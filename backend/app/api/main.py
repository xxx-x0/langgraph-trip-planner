"""FastAPI主应用

重构说明:
- 原始路由使用旧HelloAgents框架的MCP调用和Agent
- 现已切换到LangGraph框架的Agent和LangChain兼容的MCP工具
- 旧路由代码保留在routes目录中，但不再注册到FastAPI应用
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from ..config import get_settings, validate_config, print_config
from ..logger import setup_logging, log_print, LOG_FILE

# 旧路由导入 (已弃用，保留供参考)
# from .routes import trip, poi, map as map_routes

# 新路由导入 (LangGraph + LangChain MCP)
from .routes import trip_lg, poi_lg, map_lg, trip_history
from ..database import init_db

# 获取配置
settings = get_settings()

# 设置日志
setup_logging(settings.log_level)

# 创建FastAPI应用
app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="基于LangGraph框架的智能旅行规划助手API",
    docs_url="/docs",
    redoc_url="/redoc"
)

# 配置CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.get_cors_origins_list(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册路由 (LangGraph版本)
app.include_router(trip_lg.router, prefix="/api")
app.include_router(poi_lg.router, prefix="/api")
app.include_router(map_lg.router, prefix="/api")
app.include_router(trip_history.router, prefix="/api")

# 旧路由注册 (已弃用)
# app.include_router(trip.router, prefix="/api")
# app.include_router(poi.router, prefix="/api")
# app.include_router(map_routes.router, prefix="/api")


@app.on_event("startup")
async def startup_event():
    """应用启动事件"""
    await init_db()
    log_print("✅ 数据库初始化完成")
    log_print("\n" + "="*60)
    log_print(f"🚀 {settings.app_name} v{settings.app_version}")
    log_print("="*60)
    log_print(f"日志文件: {LOG_FILE}")
    
    # 打印配置信息
    print_config()
    
    # 验证配置
    try:
        validate_config()
        log_print("\n✅ 配置验证通过")
    except ValueError as e:
        log_print(f"\n❌ 配置验证失败:\n{e}", level="error")
        log_print("\n请检查.env文件并确保所有必要的配置项都已设置", level="error")
        raise
    
    log_print("\n" + "="*60)
    log_print("📚 API文档: http://localhost:8000/docs")
    log_print("📖 ReDoc文档: http://localhost:8000/redoc")
    log_print("🔧 框架: LangGraph + LangChain MCP Tools")
    log_print("="*60 + "\n")


@app.on_event("shutdown")
async def shutdown_event():
    """应用关闭事件"""
    print("\n" + "="*60)
    print("👋 应用正在关闭...")
    print("="*60 + "\n")


@app.get("/")
async def root():
    """根路径"""
    return {
        "name": settings.app_name,
        "version": settings.app_version,
        "status": "running",
        "framework": "LangGraph",
        "docs": "/docs",
        "redoc": "/redoc"
    }


@app.get("/health")
async def health():
    """健康检查"""
    return {
        "status": "healthy",
        "service": settings.app_name,
        "version": settings.app_version,
        "framework": "LangGraph"
    }


if __name__ == "__main__":
    import uvicorn
    
    uvicorn.run(
        "app.api.main:app",
        host=settings.host,
        port=settings.port,
        reload=True
    )
