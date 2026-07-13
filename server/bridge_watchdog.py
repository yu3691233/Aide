"""
watchdog.py
守护进程：自动监控并重启 phone_chat_bridge.py
如果桥接服务崩溃，自动重启。
"""
import subprocess
import sys
import time
import os
import threading

BRIDGE_DIR = os.path.dirname(os.path.abspath(__file__))
BRIDGE_SCRIPT = os.path.join(BRIDGE_DIR, "phone_chat_bridge.py")

# ── 内存阈值配置 ──
MEMORY_WARN_MB = 800
MEMORY_KILL_MB = 1600
MEMORY_CHECK_INTERVAL = 15

# 重定向自身输出到 flask_new.log 并开启行缓冲，确保父进程退出后不崩溃
try:
    if sys.platform == 'win32':
        import ctypes
        ctypes.windll.kernel32.SetConsoleTitleW("aidelink-watchdog-service")
        
    log_path = os.path.join(BRIDGE_DIR, "flask_new.log")
    # 限制日志大小，超过 5MB 则重命名备份
    try:
        if os.path.exists(log_path) and os.path.getsize(log_path) > 5 * 1024 * 1024:
            bak_path = log_path + ".bak"
            if os.path.exists(bak_path):
                os.remove(bak_path)
            os.rename(log_path, bak_path)
    except Exception:
        pass

    log_file = open(log_path, "a", encoding="utf-8", buffering=1)
    sys.stdout = log_file
    sys.stderr = log_file
except Exception:
    pass

# 打开供子进程输出使用的日志文件
try:
    log_path = os.path.join(BRIDGE_DIR, "flask_new.log")
    bridge_log = open(log_path, "a", encoding="utf-8")
except Exception:
    bridge_log = subprocess.DEVNULL

# 尝试配置控制台/管道输出为 UTF-8，防止中文乱码
try:
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')
except AttributeError:
    pass

print(f"[Watchdog] 启动守护进程，监控 {BRIDGE_SCRIPT}", flush=True)

delay = 5
max_delay = 30

# 传递 UTF-8 环境变量给子进程
env = os.environ.copy()
env["PYTHONIOENCODING"] = "utf-8"

def _memory_watcher(proc):
    """在后台线程中监控子进程内存，超过阈值则杀死并打印原因。"""
    try:
        import psutil
        p = psutil.Process(proc.pid)
        while True:
            time.sleep(MEMORY_CHECK_INTERVAL)
            if proc.poll() is not None:
                return
            try:
                mem_mb = p.memory_info().rss / 1024 / 1024
                if mem_mb > MEMORY_KILL_MB:
                    print(f"[Watchdog] 内存超限 ({mem_mb:.0f}MB > {MEMORY_KILL_MB}MB)，强制重启...", flush=True)
                    p.terminate()
                    try:
                        p.wait(timeout=5)
                    except Exception:
                        p.kill()
                    return
                elif mem_mb > MEMORY_WARN_MB:
                    print(f"[Watchdog] 内存偏高 ({mem_mb:.0f}MB)，接近阈值...", flush=True)
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                return
    except ImportError:
        print("[Watchdog] psutil 未安装，跳过内存监控", flush=True)

crash_times = []
MAX_CRASHES = 5
CRASH_WINDOW = 60

while True:
    # 崩溃/重启保护：限制在指定时间窗口内的最大重启次数
    now = time.time()
    crash_times = [t for t in crash_times if now - t < CRASH_WINDOW]
    if len(crash_times) >= MAX_CRASHES:
        print(f"[Watchdog] 错误: 桥接服务在 {CRASH_WINDOW} 秒内连续退出/崩溃达 {len(crash_times)} 次！为防资源耗尽，守护进程退出。", flush=True)
        sys.exit(1)

    print(f"[Watchdog] 正在启动桥接服务...", flush=True)
    start_time = time.time()
    
    try:
        proc = subprocess.Popen(
            [sys.executable, "-u", BRIDGE_SCRIPT],
            cwd=BRIDGE_DIR,
            env=env,
            stdout=bridge_log,
            stderr=bridge_log
        )
        t = threading.Thread(target=_memory_watcher, args=(proc,), daemon=True)
        t.start()
        proc.wait()
        code = proc.returncode
    except Exception as e:
        print(f"[Watchdog] 启动桥接服务出错: {e}", flush=True)
        code = -1
        
    run_duration = time.time() - start_time
    print(f"[Watchdog] 桥接服务退出，返回码={code}，运行时间={run_duration:.2f}秒", flush=True)
    
    # 记录本次退出时间
    if code != 0:
        crash_times.append(time.time())
    
    if run_duration < 5:
        print(f"[Watchdog] 服务异常快速退出，增加退避延迟到 {delay} 秒", flush=True)
        time.sleep(delay)
        delay = min(delay * 2, max_delay)
    else:
        delay = 5
        time.sleep(delay)
