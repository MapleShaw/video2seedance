# Video Case Analyzer for Seedance

把优质参考视频拆成可复用的生成语法，而不是只做摘要。

## 它解决什么问题？

现在很多 AI 工具能"总结视频讲了什么"，但很难回答：

- 这条视频为什么抓人？
- 它为什么看起来高级？
- 哪些结构可以迁移到别的题材？
- 怎么把这种感觉转译成 Seedance 2.0 可执行的生成方案？

这个项目就是为这个问题做的。

---

## 工作流程

```
参考视频
→ [Gemini] 视频分析 → analysis.json
→ [LLM via ZenMux] 读取 analysis.json + Seedance SKILL.md → 智能生成分镜提示词
→ shot_prompts.json / shot_prompts.md
→ 直接复制到即梦平台使用
```

**第 1 步**用 Gemini（视频理解能力强），**第 2 步**用任意 LLM（通过 ZenMux 路由，默认 Claude Sonnet）。两步解耦，模型随便换。

---

## 安装

```bash
pip install -r requirements.txt
```

## 环境变量

```bash
# 必需
export GEMINI_API_KEY="your-gemini-key"
export ZENMUX_API_KEY="your-zenmux-key"

# 可选
export ZENMUX_BASE_URL="https://zenmux.ai/api/v1"  # 默认值
export SEEDANCE_MODEL="anthropic/claude-sonnet-4.6"  # 默认值
```

## 使用

### 一键全流程（视频分析 + 提示词生成）

```bash
cd src
python gemini_video_case_analyzer.py /path/to/video.mp4
```

可选参数：
- `--model`：Gemini 分析模型（默认 `gemini-2.0-flash`）
- `--prompt-model`：提示词生成 LLM（默认 `anthropic/claude-sonnet-4.6`）
- `--output-dir`：输出目录（默认 `./output`）

```bash
# 用 Claude Opus 生成提示词
python gemini_video_case_analyzer.py video.mp4 --prompt-model anthropic/claude-opus-4.6

# 用 GPT-5.2 生成提示词
python gemini_video_case_analyzer.py video.mp4 --prompt-model openai/gpt-5.2
```

### 单独跑提示词生成（已有 analysis.json）

```bash
cd src
python shot_prompt_generator.py ../output/analysis.json

# 指定模型
python shot_prompt_generator.py ../output/analysis.json --model anthropic/claude-opus-4.6
```

---

## 可用模型（ZenMux）

| 模型 | 适合场景 |
|------|---------|
| `anthropic/claude-sonnet-4.6` | 默认，快速且质量稳定 |
| `anthropic/claude-opus-4.6` | 最强创意写作，风格把控最好 |
| `openai/gpt-5.2` | 综合能力强 |
| `openai/gpt-5.2-pro` | 深度推理 |
| `google/gemini-3-pro-preview` | 多模态 |

---

## Seedance SKILL.md

提示词生成质量取决于是否检测到 `SKILL.md`（Seedance 官方规范）。

检测路径（按顺序）：
1. `~/.openclaw/workspace/skills/seedance-prompt/SKILL.md`
2. `/usr/lib/node_modules/openclaw/skills/seedance-prompt/SKILL.md`
3. 项目根目录 `./SKILL.md`

有 SKILL.md：LLM 严格按规范生成（品质锚定、光影三层、史诗结构等）
无 SKILL.md：LLM 基于内置知识生成（质量略低但仍可用）

---

## 输出

| 文件 | 说明 |
|------|------|
| `analysis.json` | Gemini 结构化分析结果 |
| `analysis.md` | Markdown 分析报告 |
| `raw_output.txt` | Gemini 原始输出 |
| `shot_prompts.json` | 分镜提示词（结构化） |
| `shot_prompts.md` | 分镜提示词（可读版） |

---

## 核心定位

**不做什么：**
- 不做自动剪辑
- 不做视频下载器
- 不负责直接产出最终成片

**做什么：**
- 拆解视频的传播机制和视觉语言
- 生成可直接使用的 Seedance 提示词
- 为 AI 视频工作流提供可复用的中间层
