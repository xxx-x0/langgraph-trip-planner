"""日志配置模块

提供统一的日志记录功能，支持输出到文件，方便调试和查看运行状态。
"""

import logging
import sys
from pathlib import Path
from datetime import datetime

# 日志目录
LOG_DIR = Path(__file__).parent.parent / "logs"
LOG_DIR.mkdir(exist_ok=True)

# 日志文件路径
LOG_FILE = LOG_DIR / f"app_{datetime.now().strftime('%Y%m%d')}.log"

# 创建日志格式
formatter = logging.Formatter(
    '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

# 创建文件处理器
file_handler = logging.FileHandler(LOG_FILE, encoding='utf-8')
file_handler.setFormatter(formatter)

# 创建控制台处理器
console_handler = logging.StreamHandler(sys.stdout)
console_handler.setFormatter(formatter)

# 配置根日志记录器
def setup_logging(level: str = "INFO"):
    """设置日志配置"""
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, level.upper()))
    
    # 清除现有处理器
    root_logger.handlers = []
    
    # 添加处理器
    root_logger.addHandler(file_handler)
    root_logger.addHandler(console_handler)
    
    return root_logger


def get_logger(name: str) -> logging.Logger:
    """获取指定名称的日志记录器"""
    return logging.getLogger(name)


def log_print(message: str, level: str = "info"):
    """同时打印到控制台和记录到日志"""
    print(message)
    logger = get_logger("app")
    log_func = getattr(logger, level.lower(), logger.info)
    log_func(message)


# 导出常用函数
__all__ = ['setup_logging', 'get_logger', 'log_print', 'LOG_FILE']
