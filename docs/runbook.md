# agent-fleet Runbook

操作手册：从零启动到日常驾驶舰队。命令以 anaconda 安装的 console scripts 为准
（`/opt/anaconda3/bin/agent-fleet-*`，已在 PATH 上）。

> 一句话心智模型：**daemon** 是常驻管家，握着「一条待发命令」的槽位；
> 你（或大副）`stage` 一条命令进槽，再 `confirm` 才真正打进对应 cmux pane。
> stage→confirm 是唯一的安全闸，永不短路。

---

## 0. 前置条件（一次性核对）

| 依赖 | 检查命令 | 期望 |
| --- | --- | --- |
| cmux 在跑 | `cmux window.list` | 列出至少 1 个 window |
| `cmux` 在 PATH | `which cmux` | `~/.local/bin/cmux`（软链到 `/Applications/cmux.app/...`） |
| `claude` 在 PATH | `which claude` | `~/.local/bin/claude`（大副 REPL 需要） |
| repl 依赖 | `python -c "import rich, prompt_toolkit"` | 无报错（chat / 带色 board 需要） |
| 包已装 | `agent-fleet-board --help` | 打印 usage |

没装包：`pip install -e '.[dev,repl]'`（在仓库根目录）。

---

## 1. 启动 daemon（必须第一个起）

daemon 是所有 client 的 broker，不起则 stage/confirm/board 路由全部失败。

```bash
# 前台（看日志，调试用）
agent-fleet-daemon

# 后台常驻（日常用）
nohup agent-fleet-daemon >/tmp/agent-fleet-daemon.log 2>&1 &
```

校验：

```bash
pgrep -fl agent_fleet.daemon          # 看到进程
ls -l /tmp/agent-fleet.sock           # srw------- 权限 0600
```

> socket 路径可用 `AGENT_FLEET_SOCKET` 覆盖；daemon 和所有 client 必须用同一个值。

**当前状态**：daemon 已在跑（PID 30684），socket `/tmp/agent-fleet.sock` 存在。
无需重启。

---

## 2. 打开看板（看舰队有哪些船）

board 是只读全屏 TUI，**在你的真实终端里跑**，不要在别的 agent session 里跑。

```bash
agent-fleet-board            # 打印一次，退出
agent-fleet-board --watch    # 每 2 秒刷新的常驻看板（推荐放一个独立 pane）
agent-fleet-board --json     # 机器可读，给脚本用
agent-fleet-board --watch --interval 1   # 自定义刷新间隔
```

`--watch` 会把自己的 surface UUID 写进 `~/.cache/agent-fleet/board-surfaces/<uuid>`，
所以看板永远不会把自己列进舰队（退出时 atexit 自动清掉）。

每行显示：编号 → 昵称（alpha/bravo/…）→ 工作目录 → 最近一条命令 → 当前活动状态。
**昵称按 surface UUID 永久绑定，别的 pane 开关都不漂移。**

> 注意：`~/.cache/agent-fleet/nicknames.json` 目前不存在 —— 说明还没跑过一次
> board 给船分配昵称。第一次跑 `agent-fleet-board` 就会创建并分配。

---

## 3. 驾驶方式 A：键盘（确定性，无 LLM）

`say.py` 用正则解析 `<昵称> <命令>`，走同一套 socket 协议，不调 LLM、无 spinner。

```bash
# 一步到位：stage + 自动 confirm（-y）
agent-fleet-say -y "alpha echo hello-from-fleet"
agent-fleet-say -y "bravo git status"
agent-fleet-say -y "二号 git status"        # 中文编号也认

# 安全闸演示：分两步，中间可反悔
agent-fleet-say "alpha echo test"   # 只 stage，不发
agent-fleet-confirm                  # 👍 真正打进 alpha pane
agent-fleet-confirm cancel           # 👎 丢弃待发命令（替代上面那步）
```

`agent-fleet-say`（无参数）进入交互 REPL；加 `-y` 是 AUTO-COMMIT 模式。

---

## 4. 驾驶方式 B：大副 / 舰长 TUI（自然语言，自动识别 ship）

**这就是「我跟它对话、它自动识别 ship 帮我输入」的那个 TUI** —— `agent-fleet-chat`。
大副（First Mate）后端是 `claude --print`，读 board snapshot 自己判断你指的是哪条船。

```bash
agent-fleet-chat                    # 进入 REPL（全屏，在真实终端跑）
agent-fleet-chat -q "alpha 跑 pytest"   # 一次性问一句就退出
agent-fleet-chat --timeout 90       # LLM 超时秒数（默认 60）
```

进去后直接打字下令：

```
舰长 ❯ 让 alpha 跑 pytest
大副 ❯ alpha：pytest，舰长。   ✓ stage[alpha] ✓ confirm·fired
```

大副每一轮的流程：
1. 拉 board snapshot（经 cmux_control）
2. 把对话 + 看板喂给 `claude --print`，要求返回 `{reply, actions[]}` JSON
3. 按 actions 派发 `stage` / `confirm` / `cancel` 到 daemon

**不指定船名时它默认选当前焦点 pane**；指代不明会反问「哪艘船，舰长？」而不瞎发。

REPL 内置 slash 命令：

| 命令 | 作用 |
| --- | --- |
| `/board` | 打印当前看板 |
| `/last` | 上一轮的 action 执行结果 |
| `/raw` | 上一轮 LLM 原始 envelope |
| `/clear` | 清对话历史 |
| `/help` | 命令列表 |
| `/quit` `/exit` 或 Ctrl-D | 退出 |

> 换 LLM 后端：改 `chat.py` 里单个 `_call_claude` 函数即可，只要产出同样的
> `{reply, actions[]}` envelope。

---

## 5. 典型一天的流程

```bash
# ① 起 daemon（已在跑就跳过）
pgrep -f agent_fleet.daemon || nohup agent-fleet-daemon >/tmp/agent-fleet-daemon.log 2>&1 &

# ② 一个 pane 常开看板
agent-fleet-board --watch

# ③ 另一个 pane 开大副，自然语言指挥
agent-fleet-chat

# ④ 或者直接键盘秒发
agent-fleet-say -y "alpha git pull"
```

可选一键布局：`bash agent_fleet/fleet_layout.sh`（左看板 pane + 右浏览器 surface，
浏览器地址默认 `http://localhost:3000`，用 `FLEET_VOICE_URL` 覆盖）。

---

## 6. 故障排查

| 症状 | 原因 | 处理 |
| --- | --- | --- |
| client 报连不上 socket | daemon 没起 / socket 路径不一致 | `pgrep -f agent_fleet.daemon`；核对 `AGENT_FLEET_SOCKET` 两边一致 |
| `confirm` 返回 `fired:false` | 槽位空（TTL 60s 过期或已被发/被取消） | 重新 `stage` 再 `confirm` |
| 看板把自己列进舰队 | board-surfaces 标记没写上 | 确认用的是 `--watch`；检查 `~/.cache/agent-fleet/board-surfaces/` |
| 看板只看到一个窗口的船 | 跨窗口枚举没生效 | board 已用 `window.list`→`workspace.list` 修复；确认 cmux 版本 |
| chat 报缺 rich/prompt_toolkit | 没装 `[repl]` extra | `pip install -e '.[repl]'` |
| chat LLM 超时/报错 | `claude` 不在 PATH 或网络 | `which claude`；`agent-fleet-chat --timeout 90` |
| `cmux: command not found`（hook 里） | cmux 没在 PATH | 已软链 `~/.local/bin/cmux`；新开 shell 生效 |

### 手动戳协议（绕过所有 client，调试 daemon）

```bash
# 查当前槽位状态
echo '{"action":"status_route"}' | nc -U /tmp/agent-fleet.sock

# 手动 stage 再 confirm
echo '{"action":"stage_route","target":"alpha","text":"echo hi"}' | nc -U /tmp/agent-fleet.sock
echo '{"action":"confirm_route"}' | nc -U /tmp/agent-fleet.sock
```

---

## 7. 已知遗留（别踩）

`/opt/anaconda3/bin/` 里有两个**过时脚本**指向已删除的模块，跑会 ImportError：

- `agent-fleet`（旧 global agent view 入口）
- `agent-fleet-mcp`（旧 MCP 桥入口）

**不要用这俩。** 有效入口只有：`-daemon` `-board` `-say` `-confirm` `-chat` `-demo`。
要清理：`pip install -e .` 重装会刷新 entry points（pyproject 已不含这两个 script）。

---

## 命令速查

| 我想… | 命令 |
| --- | --- |
| 起管家 | `agent-fleet-daemon`（后台加 `nohup … &`） |
| 看舰队 | `agent-fleet-board --watch` |
| 键盘秒发 | `agent-fleet-say -y "<昵称> <命令>"` |
| 只 stage | `agent-fleet-say "<昵称> <命令>"` |
| 确认发出 | `agent-fleet-confirm` |
| 取消待发 | `agent-fleet-confirm cancel` |
| 自然语言指挥（舰长 TUI） | `agent-fleet-chat` |
| 一次性问一句 | `agent-fleet-chat -q "alpha 跑 pytest"` |
