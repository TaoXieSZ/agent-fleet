# agent-fleet

> 一支编码 agent 舰队的免手控制平面。通过语音或键盘，驱动跑在
> [cmux](https://github.com/manaflow-ai/cmux) 里的 Claude Code / Cursor
> 会话——每艘船有永久绑定的昵称，编号从不漂移。

```
舰长 ❯ alpha 跑 pytest
大副 ❯ alpha：pytest，舰长。   ✓ stage[alpha] ✓ confirm·fired
```

你叫一艘船的名字，下一道命令，daemon 把这条命令原文打进对应的 cmux pane，
等你按一下确认就执行。不用复制粘贴，不用切窗口，不用找标签页。

> 📐 **架构图**：[`docs/architecture.md`](docs/architecture.md) 里有 3 张
> mermaid 图（GitHub 自动渲染）；编辑版 Excalidraw 源文件在
> [`docs/diagrams/`](docs/diagrams/)，丢到 https://excalidraw.com 就能改。

---

## 为什么有这个项目

你同时在跑很多个编码 agent——这个仓库一个 Claude Code、那个仓库一个 Cursor、
一个 deploy shell、一个测试 watcher。驱动它们意味着不停切键盘+换窗口；
而 cmux 的 `workspace:N` / `surface:N` 是位置型编号，**任意一个 pane 开关
都会让所有编号漂移**——任何"session 3"的规则一旦分屏就废了。

agent-fleet 把寻址层修好了：

- 每个 cmux 终端 pane 自动得一个稳定的 **北约音标昵称**（alpha, bravo,
  charlie, …），key 是 surface UUID。这个名字伴随这个 pane 终生；别的
  pane 开开关关，alpha 还是 alpha。
- 看板**跨所有 cmux 窗口**枚举，把看板自己拆成独立窗口也不会丢 agent。
- 每行显示这艘船**正在干什么**——Claude Code 自己的 recap 或活动动词
  （`✻ Brewed for 7s` / `※ recap: …`），而不是固定的 "bypass permissions"
  banner。
- LLM REPL（**大副**，First Mate）说同一套协议，所以你可以用自然语言
  下令，没指定船时它自动选当前焦点。

## 看板样例（每 2 秒刷新）

```
┌ FLEET BOARD ───────────────────────────────────── 14:32:05 ┐
 ⚡ 2/3 active · 5h max 24% (alpha) · ctx max 12% (bravo)
▶ alpha   agent-fleet · abc                          ctx 5% · 5h 24%
│    ➜ ~/OpenSourceProjects/agent-fleet
│    ❯ run pytest
│    ✻ Brewed for 7s
│    41 passed in 0.04s
──────────────────────────────────────────────────────────────
  bravo   kaggle · 123                                ctx 12% · 5h 8%
     ➜ ~/kaggle-dir
     ⏺ Done. 41 passed.
     
  lima    ~/OpenSourceProjects
     ➜ ~/OpenSourceProjects
     
├ 3 ships · 1 focused · 0 staged ─────────────────────────────┤
└ say "alpha <cmd>" / "bravo …"  →  👍  /  confirm.py ────────┘
```

`▶` + 反白昵称 = 当前焦点；焦点船每行 body 左侧 cyan `│` 贯通整张卡。
顶部 `⚡` 行是全舰队聚合（active 数 + 5h/ctx 用量最高的船）；底部
`N ships · K focused · 0 staged` 来自 daemon `status_route` 实时查询
（daemon 没起的话最后一段会自动消失）。状态行从 pane 自己的输出里抓
（过滤掉 banner / HUD / cmux 分隔规则）；每卡底部 dim 三行是该 pane
最近的非-glyph 原始输出（shell 实况、build 进度等）。

## 快速上手

```bash
git clone https://github.com/TaoXieSZ/agent-fleet
cd agent-fleet
pip install -e '.[repl]'

# 1. 守护进程（开一个终端，保持运行）
agent-fleet-daemon

# 2. 实时看板（开第二个终端，常驻可见）
agent-fleet-board --watch

# 3. 用键盘驱动
agent-fleet-say -y "alpha echo hello"            # 暂存 + 自动确认
agent-fleet-say "alpha echo hello"               # 只暂存，等下面单独确认
agent-fleet-confirm                              # 提交暂存的那条
agent-fleet-confirm cancel                       # 丢掉它

# 4. 或用 LLM REPL（用你的 `claude` CLI，免费，不用额外 key）
agent-fleet-chat
舰长 ❯ bravo 跑 pytest
大副 ❯ bravo：pytest，舰长。
舰长 ❯ 再跑一次                                   # 大副从上下文记得是 bravo
大副 ❯ 默认走 bravo：pytest，舰长。
```

## 一窗口布局

`fleet_layout.sh` 自动在一个 cmux workspace 里摆好：左边实时看板 pane，
右边一个 browser surface（指向 `$FLEET_VOICE_URL`，默认
`http://localhost:3000`）。你的 agent session 仍是同一 window 里其它
workspace/tab：

```bash
agent_fleet/fleet_layout.sh
```

看板 pane 启动时自我注册，所以不会把自己列进船单。

## 概念表

| 词 | 含义 |
| --- | --- |
| **Ship（船）** | 一个 cmux 终端 pane（一个 Claude Code / Cursor / shell 会话）。 |
| **Nickname（昵称）** | 每艘船的稳定北约音标名（alpha…zulu）。 |
| **舰长（Captain）** | 你。 |
| **大副（First Mate）** | `chat.py` 里那个把你的人话转成路由动作的 LLM 人格。 |
| **Daemon（守护进程）** | Unix-socket broker：同时只持有一条暂存命令，按你的 confirm 才发出去。stage→confirm 拆开是安全门。 |

昵称持久化在 `~/.cache/control-plane/nicknames.json` 里（路径继承自上游 fork；
`AGENT_FLEET_NICKNAMES_PATH` 可覆盖），按 surface UUID 索引。
同一个 registry **绝不回收**已分配过的名字——船关掉，它的名字也永久退役，
将来的新船不会继承一个旧关联。

## Daemon 协议

通过 Unix socket（默认 `/tmp/agent-fleet.sock`，环境变量
`AGENT_FLEET_SOCKET` 可覆盖）传一行 JSON：

```json
{"action": "stage_route", "target": "alpha", "text": "pytest"}
  → {"ok": true}

{"action": "confirm_route"}
  → {"ok": true, "fired": true}

{"action": "cancel_route"}
  → {"ok": true, "fired": true}

{"action": "status_route"}
  → {"ok": true, "staged": {"target": "alpha", "text": "pytest", "age_s": 4.2}}
  // or {"staged": null} when nothing is pending
```

`target` 可以是昵称（`"alpha"`）、无歧义前缀（`"alph"`），或为兼容旧客户端
传 1-based 整数 / 数字串。**命名到 surface UUID 的解析发生在 fire 时**，所以
当前看板永远是 source of truth。

## 仓库结构

```
agent_fleet/
  cmux_control.py   # 跨窗口枚举 + 昵称 registry + 智能状态 + workspace.rename
  stager.py         # stage→confirm/cancel 状态机（TTL，last-wins，status() 快照）
  daemon.py         # Unix-socket broker（stage/confirm/cancel/status_route）
  board.py          # 实时 TUI 看板：box-corner 边框 + metrics 行 + 焦点 │ + tail 预览
  clawd.py          # 可选角色渲染器（Pack / Kitty / BlockArt，默认关）
  say.py            # 键盘驱动（解析 "alpha 跑 ls"）
  confirm.py        # confirm / cancel CLI（手势的键盘替身）
  chat.py           # Codex 风 LLM REPL，大副人格
  smoke_test.py     # 真 cmux 上的一次性安全验证（用临时 pane）
  demo.py           # 完整 board→stage→confirm→执行 演示
  fleet_layout.sh   # 一键 cmux 布局
docs/
  architecture.md   # 架构文档（mermaid 内嵌）
  diagrams/         # Excalidraw 源 + 生成脚本
tests/              # 33 个纯 Python 单测，不需要 cmux
```

## 状态

**v0.1 alpha。** 从
[`TaoXieSZ/claude-code-buddy`](https://github.com/TaoXieSZ/claude-code-buddy)
的 `tools/control_plane/` 抽出来独立成 repo。在那个 fork 里它跟语音前端
（Agora ConvoAI）、摄像头手势确认、StackChan 桌面外设集成过；agent-fleet
本身是**后端无关**的——任何能开 Unix socket 写 JSON 的东西都是合法客户端。

## 依赖

- 核心库：**无**（只用 Python ≥ 3.10 标准库）。
- REPL 附加（`pip install -e '.[repl]'`）：`rich`、`prompt_toolkit`。
- 运行时：[cmux](https://github.com/manaflow-ai/cmux)（终端管理器）。
- chat.py 里可选的 LLM：`$PATH` 上的 `claude` CLI（直接用你的 Claude Code
  订阅，通过 `--print --json-schema`）。要换 backend？改 `chat.py` 里一个
  `_call_claude` 函数即可。

## 环境变量

所有变量都有合理默认；设 `=0` 关掉一个开关，或换路径覆盖。

| 变量 | 默认 | 作用 |
| --- | --- | --- |
| `AGENT_FLEET_SOCKET` | `/tmp/agent-fleet.sock` | daemon Unix-socket 路径；所有客户端（say / confirm / chat / board）共用。 |
| `AGENT_FLEET_NICKNAMES_PATH` | `~/.cache/control-plane/nicknames.json` | NATO 昵称持久化文件。同一 registry 内昵称**永不回收**。 |
| `AGENT_FLEET_BOARD_REGISTRY` | `~/.cache/control-plane/board-surfaces/` | live `board.py --watch` 自注册目录（一文件一 surface UUID），用于排除自身。 |
| `AGENT_FLEET_SYNC_TITLES` | `1` | board `--watch` 是否把船昵称同步到 cmux **workspace title**（`"alpha · <原 title>"`）。`=0` 关掉。仅 single-ship workspace 被改；多 pane workspace 跳过。 |
| `AGENT_FLEET_BANNER` | `1` | board 启动时是否打印 `⚓ agent-fleet vX · N ships detected · daemon ok` 单行 banner（~1s 后被 `_CLEAR` 抹掉）。`=0` 关掉。 |
| `AGENT_FLEET_CLAWD` | _unset_ | 角色渲染器开关：`pack` / `kitty` / `block`。默认不开。详见 [`agent_fleet/clawd.py`](agent_fleet/clawd.py)。 |
| `AGENT_FLEET_CLAWD_ASSETS` | _unset_ | 配合 `AGENT_FLEET_CLAWD=kitty\|block` 用——指向 clawd-on-desk GIF 资产目录（资产**不打包**，许可证原因）。 |

## 测试

```bash
pip install -e '.[dev]'
pytest -q
```

## 许可

MIT — 详见 [LICENSE](LICENSE)。
