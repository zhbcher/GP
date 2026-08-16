# 飞书 ↔ DeepSeek Harness 网关

通过飞书给 DeepSeek Harness 下达任务，Harness 执行完成后通过飞书回复结果。

## 架构

```
飞书用户 ──发消息──▶ lark-cli event consume (监听 im.message.receive_v1)
                          │ NDJSON 流
                          ▼
                    lark_bridge.py (网关守护)
                          │ dsh --profile headless "任务"
                          ▼
                    DeepSeek Harness (执行任务)
                          │ 结果
                          ▼
飞书用户 ◀──回复消息── lark-cli im +messages-reply
```

## 文件

| 文件 | 说明 |
|---|---|
| `lark_bridge.py` | 网关守护脚本（监听→执行→回复） |
| `manage_lark_bridge.sh` | 启动/停止/状态/日志管理 |
| `com.dsh.lark-bridge.plist` | launchd 常驻配置（开机自启+崩溃重启） |

## 部署步骤

### 1. 初始化 lark-cli 认证（一次性）

```bash
lark-cli config init --new --brand feishu
# 打开输出的 URL 完成飞书应用创建/授权
lark-cli auth status   # 确认 ok:true
```

### 2. 测试网关

```bash
cd /Users/zhoubo/GP/lark-bridge
python3 lark_bridge.py --test "2的10次方是多少"   # 不依赖飞书，验证 headless 链路
```

### 3. 启动网关（常驻）

```bash
./manage_lark_bridge.sh start      # 前台守护启动
tail -f lark_bridge.log            # 查看日志
```

或 launchd 常驻（开机自启）：

```bash
cp com.dsh.lark-bridge.plist ~/Library/LaunchAgents/
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.dsh.lark-bridge.plist
```

### 4. 端到端验证

在飞书里给机器人发消息（如 "2的10次方是多少"），机器人应回复结果。

## 配置项（环境变量）

| 变量 | 默认值 | 说明 |
|---|---|---|
| `DSH_WORK_DIR` | `/Users/zhoubo/deepseek` | 任务会话工作目录（headless Agent 的 cwd，任务文件都落在这里） |
| `DSH_BIN` | dsh lib/bin.js 路径 | dsh 可执行文件 |
| `HEADLESS_TIMEOUT_S` | 900 | 任务超时（秒） |
| `MAX_TASK_LEN` | 4000 | 任务文本长度上限 |

## 注意事项

- **网关是单实例的**：`lark_bridge.py` 启动时会检查 pid 锁（`lark_bridge.pid`），若已有实例在运行会直接退出；`manage_lark_bridge.sh start` 也会先检测。**不要同时用 launchd 和手动脚本启动网关**，否则同一条飞书消息会被回复两次。
- launchd 的 `KeepAlive` 配置为「仅在异常退出时重启」（`SuccessfulExit=false`），被单实例保护正常退出的实例不会触发重启循环。
- 网关在用户终端/launchd 环境运行（headless 需访问 ~/.dsh，不能在受限沙箱内跑）
- 事件 `im.message.receive_v1` 需要飞书应用启用「接收消息」事件 + `im:message.p2p_msg:readonly` 权限
- 任务串行执行（简单可靠），超时自动回复提示
