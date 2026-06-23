<div align="center">

<img src="assets/logo.png" alt="logo" width="76"/>

# 🚗 RoadTrip Navigator · 北美自驾规划

### 一个把"起点 + 天数"变成照着开就能走完的自驾行程的 AI Agent Skill。

[English](README.md) · **简体中文**

[![install: /plugin marketplace add](https://img.shields.io/badge/install-%2Fplugin%20marketplace%20add-c2641a?style=flat-square)](#-安装)
[![works with Claude Code + 16 agents](https://img.shields.io/badge/支持-Claude%20Code%20%2B%2016%20种%20agent-1f6f8b?style=flat-square)](#-安装)
[![no API key required](https://img.shields.io/badge/API%20Key-无需-2e7d4f?style=flat-square)](#可选-api-key)
[![license: MIT](https://img.shields.io/badge/license-MIT-555?style=flat-square)](LICENSE)
[![PRs welcome](https://img.shields.io/badge/PRs-welcome-7d3a13?style=flat-square)](#-参与贡献)

<br/>

<img src="docs/og.png" alt="RoadTrip Navigator" width="860"/>

</div>

---

北美自驾的核心是**车**，不是航班：*今天开几个小时、晚上睡哪、油/电够不够、路通不通。*
RoadTrip Navigator 就是围绕这几件事来规划，并生成一份**地图优先、可离线、手机可打开**的单文件 HTML 行程页。

> ⚡ **在 Claude Code 安装：** `/plugin marketplace add Waybox-AI/roadtrip-skill` → `/plugin install roadtrip-navigator@roadtrip-skill`

## ⚡ 安装

作为插件装进 **Claude Code** —— 两条命令，无需任何 Key：

```text
/plugin marketplace add Waybox-AI/roadtrip-skill
/plugin install roadtrip-navigator@roadtrip-skill
```

<details>
<summary>其他安装方式</summary>

```bash
# 手动 —— 直接放进 skills 目录
git clone https://github.com/Waybox-AI/roadtrip-skill
cp -r roadtrip-skill ~/.claude/skills/roadtrip-navigator   # 用户级
# 或放到 .claude/skills/ 供单个项目使用
```

当你的需求命中自驾相关触发词（*road trip、self-drive、自驾、国家公园、EV road trip、
RV trip、风景道…*）时，agent 会自动加载这个 skill。运行无需任何 Key。
</details>

然后直接对你的 agent 说：

> *"帮我规划一条从拉斯维加斯出发、7 天的西南国家公园自驾环线，2 个成人，9 月，燃油 SUV。"*

## ✨ 差异化在哪

大多数"AI 行程规划"只给你一堆景点清单。这个 skill 把纯模型最容易翻车的**五件事**做对了：

| | 普通 AI 行程 | **RoadTrip Navigator** |
|---|---|---|
| **每日驾驶** | 一串景点愿望清单 | 按合理日驾上限**切分成天**、安排过夜城，并校验*"天黑前到"*、*"不撞景点关门"* |
| **预约** | "记得早点订！" | **倒推待办清单**——精确到*"几号前订"*（营地约 6 个月、园内住宿约 13 个月、timed-entry），并指向**正确的系统**（Recreation.gov / ReserveCalifornia / Parks Canada） |
| **油 / 电** | 直接忽略 | 长无人区补能提醒；EV 给出**逐段充电走廊** + 电量(SoC)模拟 + 冬季掉电 |
| **季节** | 笼统天气 | **识别封路**——冬季山口（Going-to-the-Sun、Tioga、Trail Ridge）、野火/暴雪 → 改线 |
| **时区 / 跨境** | 到达时间算错 | **跨时区校正**到达时间；US↔CA↔MX **证件 / 保险 / 等待**清单 |

产出是一份单文件 HTML：**Leaflet/OpenStreetMap 路线图**（编号停靠点 + 一键跳 Google/Apple
导航）、**每日时间轴**、**预约倒推**、**带可靠度分级的预算**——完全离线友好。

## 🧭 功能

- **两种入口** —— *轻*（给"起点 + 区域 + 天数"让它规划）或 *重*（丢一份现成路线让它核实补全）。
- **多路线对比** —— A/B 对比表（里程、天数、驾驶强度、最佳季节、花费），高亮选中路线。
- **跨境模块** —— 每个口岸的证件、保险（美国保险在加拿大有效、在墨西哥**无效**）、海关、单位切换（mi/°F/USD ⇄ km/°C/CAD）。
- **EV 充电走廊** —— 逐段电量模拟、建议充到几 %、充电桩功率、冬季掉电选项。
- **可靠度分级** —— 每个数字标注 *实查 / 参考 / 估算*。
- **零 Key、可离线运行** —— 每个数据源都有 web search 兜底，地图也会优雅降级。

## 🗺️ 样例行程

打开内置的精选成品（在线 Demo 上也能点开）：

| 行程 | 主题 | 亮点 |
|---|---|---|
| **西南大环线 · 7 天** | 沙漠 | 拉斯维加斯 → Zion → Bryce → Page → 大峡谷，门票/年票倒推 |
| **Sunnyvale → 太浩湖 · 3 天** | 山地 | US-50/I-80 环线、ReserveCalifornia、Sierra 雪情/雪链风险 |
| **西雅图 → 温哥华 EV · 4 天** | 森林 | 跨境清单 + EV 充电走廊 + 路线对比 |

## ⚙️ 工作原理

```
请求 ──► scripts/helper.py ──► 7 步工作流 (SKILL.md)
           (要素/模式/区域)      ├─ 路线 + 每日分段
                                ├─ 并行调研 (tools/、web search)
                                ├─ 预约倒推
                                └─ 预算（分级）
                                     │
                     tripData.json ──┴──► assets/generate.py ──► trip.html
```

- **数据/视图分离** —— 数据先落 `tripData.json`，再由 `generate.py` 注入
  `assets/template.html`，可随时改数据重渲染。
- **子 agent 调研** —— 优先调官方/免费 API（NPS、NWS、Recreation.gov、Open Charge Map），失败再退回 web search。

本地试跑：

```bash
python3 assets/generate.py assets/tripData.example.json -o trip.html   # 西南 7 天
python3 scripts/helper.py "from Las Vegas, 7 days, 2 adults, gas, southwest loop"
python3 tools/charging_client.py --corridor                            # EV 电量模拟
```

### 可选 API Key

全部可选，没有时自动退回 web search。

| 变量 | 用于 | 免费申请 |
|---|---|---|
| `NPS_API_KEY` | 国家公园信息 | nps.gov/subjects/developer |
| `OCM_API_KEY` | EV 充电桩 | openchargemap.org |
| `OPENWEATHER_API_KEY` | 天气兜底 | openweathermap.org |

NWS 天气、OSRM 路线、OpenStreetMap 瓦片、Recreation.gov 链接均**无需 Key**。

## 🧱 项目结构

```
.claude-plugin/   plugin.json + marketplace.json（Claude Code 插件清单）
SKILL.md          入口：触发词、两种模式、7 步工作流
reference.md      tripData schema、可靠度分级、工具路由表
examples.md       典型问法示例（轻/重/EV/跨境）
assets/           generate.py + template.html + 3 个 demo 行程
scripts/helper.py 要素解析、模式/区域识别、路线对比
tools/            各数据源 client，每个都有 web search 兜底
```

## 🙅 诚实边界

它**不承诺**：实时油价/电价精确、充电桩实时占用、分钟级实时路况、营地实时余位、替代导航。
这些请以官方 App / Recreation.gov / 导航实时为准。每份行程都带免责声明，提示出行前核实官方信息。

## 🤝 参与贡献

欢迎提 Issue / PR —— 新增区域配色、某州 DOT 封路数据、新的 `tools/` client，或一条样例行程。
skill 无需任何 Key 即可运行，非常好上手。

## 📄 许可证

[MIT](LICENSE) © yang-hong
