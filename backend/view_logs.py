"""查看日志文件的便捷脚本"""

import sys
from pathlib import Path
from datetime import datetime

def view_latest_logs(lines: int = 50):
    """查看最新的日志内容"""
    log_dir = Path(__file__).parent / "logs"
    
    if not log_dir.exists():
        print("❌ 日志目录不存在")
        return
    
    # 获取今天的日志文件
    today = datetime.now().strftime('%Y%m%d')
    log_file = log_dir / f"app_{today}.log"
    
    if not log_file.exists():
        print(f"❌ 今天的日志文件不存在: {log_file}")
        # 列出所有日志文件
        log_files = sorted(log_dir.glob("app_*.log"))
        if log_files:
            print("\n可用的日志文件:")
            for f in log_files:
                print(f"  - {f.name}")
        return
    
    print(f"📄 查看日志文件: {log_file}")
    print(f"📊 显示最后 {lines} 行\n")
    print("="*80)
    
    try:
        with open(log_file, 'r', encoding='utf-8') as f:
            all_lines = f.readlines()
            # 显示最后N行
            for line in all_lines[-lines:]:
                print(line.rstrip())
    except Exception as e:
        print(f"❌ 读取日志失败: {e}")
    
    print("="*80)


if __name__ == "__main__":
    # 获取命令行参数
    lines = 50
    if len(sys.argv) > 1:
        try:
            lines = int(sys.argv[1])
        except ValueError:
            pass
    
    view_latest_logs(lines)
