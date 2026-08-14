# 服务状态报告

## 问题修复

### 根本原因
1. **Vite 只在 IPv6 监听** - 浏览器无法通过 IPv4 访问
2. **缺少 registerHotkey 导入** - 导致 JS 运行时错误
3. **cron 任务 PATH 问题** - 自动重启脚本找不到 npm 命令

### 已实施的修复

1. **网络配置**
   - 修改 `vite.config.ts` 添加 `host: '0.0.0.0'`
   - 支持 IPv4/IPv6 双栈访问

2. **代码修复**
   - 添加 `registerHotkey` 导入到 `annotationOverlay.ts`
   - 清理重复的 Vite 进程

3. **服务管理**
   - 创建 `/Users/zhoubo/GP/manage.sh` - 手动管理服务
   - 创建 `/Users/zhoubo/GP/monitor_services.sh` - 自动监控
   - 注册 launchd agents - 系统级持久化

## 当前状态

| 服务 | 端口 | 状态 | PID |
|------|------|------|-----|
| 前端 (Vite) | 5173 | ✓ 运行中 | $(lsof -t -i :5173 | head -1) |
| 后端 (FastAPI) | 8000 | ✓ 运行中 | $(lsof -t -i :8000 | head -1) |

## 访问地址

- **本地**: http://localhost:5173/
- **局域网**: http://192.168.1.34:5173/

## 管理命令

```bash
# 查看服务状态
/Users/zhoubo/GP/manage.sh status

# 启动服务
/Users/zhoubo/GP/manage.sh start

# 停止服务
/Users/zhoubo/GP/manage.sh stop

# 重启服务
/Users/zhoubo/GP/manage.sh restart

# 查看监控日志
tail -f /tmp/service_monitor_$(date +%Y%m%d).log

# 查看系统日志
tail -f /tmp/gp-frontend.log /tmp/gp-backend.log
```

## 自动恢复机制

1. **launchd KeepAlive** - 服务崩溃后自动重启
2. **监控脚本** - 每30秒检查一次，内存超400MB自动重启
3. **日志追踪** - 所有操作记录到 /tmp/service_monitor_*.log

## 故障排查

如果服务再次挂掉：

1. 检查日志
```bash
tail -50 /tmp/vite.log
tail -50 /tmp/uvicorn.log
tail -50 /tmp/service_monitor_*.log
```

2. 手动重启
```bash
/Users/zhoubo/GP/manage.sh restart
```

3. 检查系统资源
```bash
top -l 1 | grep "PhysMem"
vm_stat | head -5
```
