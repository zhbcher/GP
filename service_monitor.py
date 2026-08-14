#!/usr/bin/env python3
import subprocess
import time
import os
import signal

FRONTEND_DIR = "/Users/zhoubo/GP/frontend"
BACKEND_DIR = "/Users/zhoubo/GP/backend"
LOG_FILE = "/tmp/service_monitor.log"

def log(msg):
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{timestamp}] {msg}"
    print(line)
    with open(LOG_FILE, "a") as f:
        f.write(line + "\n")

def is_port_listening(port):
    try:
        result = subprocess.run(
            ["lsof", "-i", f":{port}"],
            capture_output=True,
            text=True
        )
        return "LISTEN" in result.stdout
    except:
        return False

def get_pid(port):
    try:
        result = subprocess.run(
            ["lsof", "-t", "-i", f":{port}"],
            capture_output=True,
            text=True
        )
        return result.stdout.strip().split("\n")[0] if result.stdout.strip() else None
    except:
        return None

def get_memory_mb(pid):
    try:
        result = subprocess.run(
            ["ps", "-p", pid, "-o", "rss="],
            capture_output=True,
            text=True
        )
        return int(result.stdout.strip()) // 1024
    except:
        return 0

def start_frontend():
    log("启动前端服务...")
    os.chdir(FRONTEND_DIR)
    subprocess.Popen(
        ["npm", "run", "dev"],
        stdout=open("/tmp/vite.log", "w"),
        stderr=subprocess.STDOUT
    )
    time.sleep(3)
    if is_port_listening(5173):
        log(f"前端启动成功 (PID: {get_pid(5173)})")
        return True
    else:
        log("前端启动失败")
        return False

def start_backend():
    log("启动后端服务...")
    os.chdir(BACKEND_DIR)
    subprocess.Popen(
        ["source", ".venv/bin/activate", "python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"],
        stdout=open("/tmp/uvicorn.log", "w"),
        stderr=subprocess.STDOUT
    )
    time.sleep(3)
    if is_port_listening(8000):
        log(f"后端启动成功 (PID: {get_pid(8000)})")
        return True
    else:
        log("后端启动失败")
        return False

def main():
    log("服务监控器启动")
    
    # 启动服务
    start_frontend()
    start_backend()
    
    # 主循环
    while True:
        time.sleep(30)
        
        # 检查前端
        if not is_port_listening(5173):
            log("前端服务断开，重启中...")
            start_frontend()
        else:
            pid = get_pid(5173)
            if pid:
                mem = get_memory_mb(pid)
                if mem > 500:  # 超过500MB内存
                    log(f"前端内存过高 ({mem}MB)，重启...")
                    os.system(f"kill {pid}")
                    time.sleep(2)
                    start_frontend()
        
        # 检查后端
        if not is_port_listening(8000):
            log("后端服务断开，重启中...")
            start_backend()

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        log("监控器停止")
    except Exception as e:
        log(f"错误: {e}")
        time.sleep(60)
