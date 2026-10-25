# Video Case Analyzer for Seedance

![Python](https://img.shields.io/badge/python-3.10%2B-3776AB?logo=python&logoColor=white)
![FFmpeg](https://img.shields.io/badge/requires-ffmpeg-007808?logo=ffmpeg&logoColor=white)
![Seedance](https://img.shields.io/badge/target-Seedance%202.0-ff6a00)
![LLM](https://img.shields.io/badge/LLM-Gemini%20%7C%20ZenMux-8e44ad)
![Report](https://img.shields.io/badge/output-offline%20HTML%20report-2c7be5)

> 把优质参考视频拆成可复用的生成语法，而不是只做摘要。

输入一条参考视频，输出结构化分析（`analysis.json`）、可直接粘贴到 Seedance 的 A/B/C 三版提示词（`prompts.md`），以及一个可离线打开的交互式可视化报告（`report.html`）。

---

## 目录

- [解决什么问题](#解决什么问题)
- [工作流程](#工作流程)
- [环境准备](#环境准备)
- [快速开始：从视频到报告](#快速开始从视频到报告)
- [其他运行方式](#其他运行方式)
- [可视化报告](#可视化报告)
- [输出文件](#输出文件)
- [目录结构](#目录结构)
- [配置参考](#配置参考)
- [测试](#测试)
- [核心定位](#核心定位)
- [致谢](#致谢)

---

## 解决什么问题

很多 AI 工具能「总结视频讲了什么」，但很难回答：

- 这条视频为什么抓人？
- 它为什么看起来高级？
- 哪些结构可以迁移到别的题材？
- 怎么把这种感觉转译成 Seedance 2.0 可执行的生成方案？

本项目就是为这些问题设计的。

---

## 工作流程

```text
参考视频（本地文件 / 分享链接）
  → ① 分析：Gemini / 抽帧 + 多模态 LLM / Agent 读图   → analysis.json
  → ② 提示词生成：LLM + Seedance SKILL.md             → shot_prompts.json + prompts.md
  → ③ 报告：ffmpeg 实测 + 分析结论对账                 → report.html
```

第 ① 步有三种可互换的分析路径，产出同一套 `analysis.json`：

| 路径 | 方式 | 触发方式 |
|------|------|----------|
| **A. Gemini**（默认） | 视频直接上传给 Gemini | `--analyzer gemini` |
| **B. frames** | 本地 ffmpeg 抽关键帧 + 多模态 LLM（ZenMux） | `--analyzer frames` |
| **C. Agent 对话内**（推荐） | 抽帧后由对话中的 Agent 读图并手写 `analysis.json` | 见 [Agent 对话内路径](#agent-对话内路径推荐) |

第 ② 步通过 ZenMux 路由任意 LLM（默认 Claude Sonnet），两步解耦，模型可随意替换。第 ③ 步只依赖 ffmpeg，无需 API Key。

---

## 环境准备

### 1. 系统依赖

| 依赖 | 用途 | 安装（macOS） |
|------|------|---------------|
| Python 3.10+ | 运行脚本 | `brew install python` |
| ffmpeg / ffprobe | 抽帧、切点与响度实测、播放代理转码 | `brew install ffmpeg` |
| yt-dlp（可选） | 从分享链接下载视频 | `pip install yt-dlp` |

### 2. Python 依赖

```bash
git clone https://github.com/MapleShaw/video2seedance.git
cd video2seedance
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 3. 环境变量

在项目根目录创建 `.env`（已被 `.gitignore` 忽略，不会提交），或直接 `export`：

```bash
# 必需（按所用路径）
GEMINI_API_KEY=your-gemini-key        # 路径 A
ZENMUX_API_KEY=your-zenmux-key        # 路径 B 与第 ② 步

# 可选
ZENMUX_BASE_URL=https://zenmux.ai/api/v1
SEEDANCE_MODEL=anthropic/claude-sonnet-4.6
SEEDANCE_SKILL_PATH=/path/to/seedance-prompt-skill/SKILL.md
```

> 只想生成报告（已有 `analysis.json`）时无需任何 API Key。

---

## 快速开始：从视频到报告

以下示例把一条视频分析成 case `0822_003`。约定：原视频放在 `downloads/<MMDD>/<NNN>.mp4`，产物放在 `output/<MMDD>_<NNN>/`，这样报告可以自动找到原视频。

**第 1 步：准备视频**

```bash
cd src
# 方式一：从分享链接下载（抖音 / B 站 / YouTube 等）
python video_downloader.py "https://v.douyin.com/xxxxx/" --out-dir ../downloads/0822 --name 003

# 方式二：手动放置本地视频
mkdir -p ../downloads/0822 && cp /path/to/video.mp4 ../downloads/0822/003.mp4
```

**第 2 步：一键分析 + 生成提示词 + 生成报告**

```bash
python gemini_video_case_analyzer.py ../downloads/0822/003.mp4 --output-dir ../output/0822_003
```

**第 3 步：查看报告**

```bash
open ../output/0822_003/report.html   # Windows: start / Linux: xdg-open
```

报告为单文件网页，双击即可离线打开。多个 case 的总览页可用以下命令生成：

```bash
python report_builder.py --all ../output     # 重建所有报告 + output/index.html
open ../output/index.html
```

**第 4 步：使用提示词**

打开 `output/0822_003/prompts.md`（或报告中的「A/B/C Prompt」标签页一键复制），选择一个版本：

1. 用「人物参考图 Prompt」生成人物图，作为 `@主体` 上传；
2. 准备一张独立场景图，作为 `@场景` 上传；
3. 粘贴「视频 Prompt」到 Seedance 生成。建议先用 720p 出片，定稿后再放大。

---

## 其他运行方式

### Agent 对话内路径（推荐）

由对话中的 Agent（如 CodeBuddy / Claude Code）亲自读图分析，质量最高：

```bash
cd src
# 1. 只抽帧，不调用 LLM
python frame_analyzer.py ../downloads/0822/003.mp4 --out-dir ../output/0822_003/frames --max-frames 8

# 2. 让 Agent 逐帧读图，按 src/schema.py 的结构写出 ../output/0822_003/analysis.json

# 3. 生成提示词，并自动生成 report.html
python shot_prompt_generator.py ../output/0822_003/analysis.json \
  --output-dir ../output/0822_003 --video ../downloads/0822/003.mp4
```

### frames 路径

```bash
python gemini_video_case_analyzer.py video.mp4 --analyzer frames \
  --vision-model openai/gpt-5.2 --max-frames 24 --output-dir ../output/<case>
```

### 只重跑提示词（已有 analysis.json）

```bash
python shot_prompt_generator.py ../output/<case>/analysis.json --output-dir ../output/<case> \
  --model anthropic/claude-opus-4.6 --style-hint "..."
```

### 只重建报告

修改了 `analysis.json` 或 `prompts.md` 后，重建报告即可同步：

```bash
python report_builder.py ../output/<case>                        # 自动从 downloads/ 找原视频
python report_builder.py ../output/<case> --video /path/to.mp4   # 显式指定原视频
python report_builder.py --index ../output                       # 只刷新总览页
```

---

## 可视化报告

`report.html` 是单文件交互页，关键帧内嵌，原视频按相对路径引用：

| 模块 | 内容 |
|------|------|
| 监看台 | 播放器与当前节拍联动；循环、0.25×–2× 变速、逐帧步进、画中画 |
| 多轨节奏仪表盘 | 实测切点 / 分析节拍 / 注意力 / 画面运动 / 响度与起音点 / 亮度共用时间轴；切点落在起音点上标绿 |
| 节拍拆解 | 每拍首尾关键帧并排，运镜描述旁标注实测运动量；支持筛选、搜索、大图 |
| 机制 / 视觉 / 节奏 / 迁移骨架 | `analysis.json` 全部结论；色板同时展示像素聚类实测色 |
| A/B/C Prompt | 分版切换、分段复制或整版复制；自动标出违反「禁止时间戳」约定的写法 |
| 质量对账 | 片长、画幅、镜头数、运镜、峰值时刻、Prompt 约定，逐条与实测比对 |

快捷键：`Space` 播放、`← →` 切节拍、`J L` ±1 秒、`, .` 逐帧、`R` 循环、`P` 画中画、`/` 搜索、`1-3` 切 Prompt 版本、`T` 明暗主题、`?` 帮助。

> 报告引用原视频的相对路径，移动 `output/` 时请连同 `downloads/` 一起移动，或使用 `--video` 重新指定。

---

## 输出文件

每个 case 目录 `output/<case>/` 包含：

| 文件 | 说明 |
|------|------|
| `analysis.json` | 结构化分析结果（第 ① 步） |
| `analysis.md` | Markdown 分析报告 |
| `shot_prompts.json` | 提示词结构化中间产物 |
| `prompts.md` | 最终交付物：A/B/C 三版人物参考图 Prompt + 视频 Prompt |
| `report.html` | 交互式可视化报告 |
| `measure.json` | ffmpeg 实测缓存（机器生成，勿手改；`--force` 强制重测） |
| `frames/`、`report_assets/` | 关键帧、胶片条、HEVC/4K 源的 720p 播放代理 |

> `output/`、`downloads/`、`goodcase/` 与所有视频文件均已加入 `.gitignore`，仓库只包含代码与文档。克隆后按上述步骤运行即可在本地得到同样的报告。

---

## 目录结构

```text
.
├── SKILL.md                     # Agent Skill 定义（分析规范与三种路径说明）
├── requirements.txt
├── examples/                    # 示例输出（analysis.json / 报告样例）
├── src/
│   ├── gemini_video_case_analyzer.py  # 一键全流程入口
│   ├── video_downloader.py      # 分享链接 → 本地视频
│   ├── frame_analyzer.py        # ffmpeg 抽帧 / frames 路径分析
│   ├── shot_prompt_generator.py # 第 ② 步：生成 A/B/C 提示词
│   ├── report_builder.py        # 第 ③ 步：生成 report.html / index.html
│   ├── report_assets/           # 报告模板、样式与脚本
│   ├── schema.py                # analysis.json 结构定义
│   └── validation.py ...        # 校验与风格约束
├── tests/
├── downloads/                   # 本地视频（不提交）
└── output/                      # 分析产物（不提交）
```

---

## 配置参考

### 主要命令行参数（`gemini_video_case_analyzer.py`）

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `--output-dir` | `./output` | 输出目录 |
| `--analyzer` | `gemini` | `gemini` / `frames` |
| `--model` | `gemini-2.5-flash` | Gemini 分析模型 |
| `--vision-model` | `anthropic/claude-sonnet-4.6` | frames 路径多模态模型 |
| `--max-frames` / `--frame-method` | `16` / `interval` | 抽帧数量与策略（`interval` / `scene`） |
| `--prompt-model` | `anthropic/claude-sonnet-4.6` | 提示词生成模型 |
| `--style-hint` | — | 注入 case 特定风格要求 |

`report_builder.py`：`--threshold` 场景切点阈值（默认 0.3，暗场或慢节奏建议 0.15）、`--no-proxy` 关闭 720p 代理、`--force` 忽略缓存。

### 可用模型（ZenMux）

| 模型 | 适合场景 |
|------|----------|
| `anthropic/claude-sonnet-4.6` | 默认，速度与质量平衡 |
| `anthropic/claude-opus-4.6` | 创意写作与风格把控最佳 |
| `openai/gpt-5.2` | 综合能力强 |
| `openai/gpt-5.2-pro` | 深度推理 |
| `google/gemini-3-pro-preview` | 多模态 |

### Seedance SKILL.md

提示词质量取决于是否加载 Seedance 规范 `SKILL.md`，检测顺序：

1. 环境变量 `SEEDANCE_SKILL_PATH`（推荐）
2. 项目根目录 `./SKILL.md`

未检测到时使用模型内置知识生成，质量略低但仍可用。

### 提示词约定

最终提示词统一为轻量四段式：

```text
主体：@主体/角色参考图
场景：@场景参考图
音乐：参考近期抖音热门 BGM 方向，写明曲目/类型、BPM、音色、情绪和卡点；同时生成对应音效
连续动作 / Shot 描述
```

- BGM 默认启用；明确不要 BGM 时追加 `--music-mode off`。
- 不使用拼接式分镜故事板，不写 `[0-3秒]` 类时间戳，不重复参考图已表达的细节。

---

## 测试

```bash
python -m unittest discover -s tests
```

---

## 核心定位

| 不做 | 做 |
|------|----|
| 自动剪辑 | 拆解视频的传播机制与视觉语言 |
| 直接产出最终成片 | 生成可直接使用的 Seedance 提示词 |
| 通用视频下载服务 | 为 AI 视频工作流提供可复用的中间层 |

---

## 致谢

可视化报告的交互思路（单文件报告、播放器与节拍联动、「代码实测 + 模型判断」对账）参考了 [reelbench-skills](https://github.com/eternityspring/reelbench-skills)（Apache-2.0）。本仓库的代码与视觉设计为独立实现。
