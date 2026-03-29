---
name: video-case-analyzer-for-seedance
description: >
  分析优质参考视频，提炼传播机制、视觉语言、节奏结构与可迁移生成骨架，
  并转译为可供 Seedance 2.0 或下游 Agent 使用的结构化结果。
---

# Video Case Analyzer for Seedance

一个面向 AI 视频工作流的“案例分析器” Skill。

它不负责剪辑，不负责直接生成最终成片。  
它负责把一个参考视频拆成：

1. 这条视频为什么抓人
2. 哪些视觉/节奏/情绪机制在起作用
3. 哪些元素必须保留，哪些可以替换
4. 如何转译为 Seedance 2.0 可执行的生成方案

---

## 何时使用

适用于以下需求：

- “帮我拆解这个优质视频案例”
- “分析这条视频为什么高级 / 为什么像爆款”
- “提炼成可给 Seedance 用的生成骨架”
- “我不需要剪辑，只想拿分析结果去做 AI 视频生成”
- “我要把参考视频转成脚本 / 分镜 / 提示词依据”

---

## 不适用

以下情况不适合使用本 Skill：

- 自动粗剪 / 自动选片
- 多段素材拼接
- 影视级逐帧镜头技术分析
- 纯字幕摘要
- 直接输出最终视频成片

---

## 输入

### 必填
- `video_path_or_url`
  - 本地视频路径，或 Gemini CLI 可访问的视频 URL

### 可选
- `goal`
  - 用户要借鉴什么
  - 例：拆高级感、拆爆款感、提炼 Seedance 生成骨架

- `target_platform`
  - `seedance`
  - `seedance+script`
  - `seedance+storyboard`
  - `generic`

- `output_depth`
  - `fast`
  - `standard`
  - `deep`

- `focus`
  - 可多选：
    - `hook`
    - `rhythm`
    - `camera`
    - `visual_style`
    - `emotion`
    - `viral_mechanics`
    - `seedance_translation`

- `variant_direction`
  - 希望迁移的方向
  - 例：东方奇幻 / 科技产品广告 / 小红书女性向 / 赛博压迫感

---

## 输出

输出为两部分：

### 1. 结构化 JSON
供后续 Agent / 工作流接力使用

### 2. Markdown 报告
供人工阅读、复盘、继续转译使用

---

## 核心分析目标

本 Skill 不回答“视频讲了什么”，而回答：

1. 这条视频为什么让人停留？
2. 它的 hook 在哪里？
3. 它的节奏与情绪是如何推进的？
4. 它为什么看起来贵、强、上头？
5. 如果换角色 / 换场景 / 换题材，哪些结构仍然成立？
6. 对 Seedance 来说，应该如何转译成生成语言？

---

## 分析维度

### 第 1 层：客观观察
- 时长 / 比例 / 镜头数
- 时间轴事件拆解
- 主体 / 场景 / 动作
- 镜头语言
- 音画关系

### 第 2 层：机制判断
- hook 类型
- 注意力维持机制
- 节奏与峰值点
- 情绪曲线
- 高级感来源
- 传播性来源

### 第 3 层：抽象迁移
- 必须保留的元素
- 可替换的元素
- 不建议照抄的元素
- 抽象成通用生成骨架

### 第 4 层：Seedance 转译
- 推荐生成模式
- 提示词结构模板
- 是否需要首帧图
- 是否需要参考视频
- 是否建议拆段生成
- 风险点与翻车点

---

## 输出 Schema

```json
{
  "meta": {
    "title": "string",
    "duration_seconds": 0,
    "aspect_ratio": "string",
    "estimated_shot_count": 0,
    "pace": "slow|medium|fast|mixed",
    "primary_format": "ad|short-film|music-visual|ugc|talking-head|motion-design|other"
  },
  "summary": {
    "one_sentence": "string",
    "core_appeal": "string",
    "likely_intent": "string"
  },
  "timeline": [
    {
      "start": 0,
      "end": 0,
      "visual_event": "string",
      "subject_action": "string",
      "camera_action": "string",
      "audio_event": "string",
      "narrative_function": "hook|setup|build|twist|payoff|ending",
      "attention_level": 1
    }
  ],
  "visual_language": {
    "style_keywords": ["string"],
    "palette": ["string"],
    "lighting": ["string"],
    "texture_fx": ["string"],
    "environment_traits": ["string"],
    "subject_design_traits": ["string"]
  },
  "rhythm_structure": {
    "hook_window": "string",
    "peak_moments": [
      {
        "time": 0,
        "reason": "string"
      }
    ],
    "pattern": "string",
    "intensity_curve": "string"
  },
  "camera_language": {
    "shot_types": ["string"],
    "movement_patterns": ["string"],
    "framing_traits": ["string"],
    "continuity_strategy": "string"
  },
  "emotion_and_psychology": {
    "dominant_emotion": "string",
    "emotion_curve": "string",
    "viewer_pull_factors": ["string"],
    "why_it_feels_premium": ["string"]
  },
  "viral_mechanics": {
    "hook_type": "string",
    "retention_drivers": ["string"],
    "shareability_drivers": ["string"],
    "repeat_watch_drivers": ["string"]
  },
  "transferable_pattern": {
    "must_keep": ["string"],
    "replaceable": ["string"],
    "do_not_copy_literally": ["string"],
    "abstract_pattern": "string"
  },
  "seedance_translation": {
    "recommended_mode": "pure_text|first_frame_plus_text|reference_video_plus_image|multi-stage",
    "why": "string",
    "seedance_ready_prompt_template": "string",
    "shot_plan_needed": true,
    "reference_asset_suggestion": ["string"],
    "risk_points": ["string"]
  },
  "next_step_assets": {
    "script_needed": true,
    "storyboard_needed": true,
    "first_frame_prompt_needed": true,
    "variants": [
      {
        "name": "string",
        "direction": "string",
        "what_changes": ["string"],
        "what_stays": ["string"]
      }
    ]
  }
}
```

---

## 输出 Markdown 结构

```md
# 视频案例分析报告

## 1. 一句话结论
## 2. 视频概览
## 3. 时间轴拆解
## 4. 它为什么成立
## 5. 视觉语言
## 6. 镜头与节奏语言
## 7. 可迁移骨架
## 8. 转译给 Seedance
## 9. 三个变体方向
## 10. 下一步建议
```

---

## 执行原则

- 不做空泛影评
- 不止做摘要
- 必须区分“表层题材”和“底层机制”
- 必须输出“可迁移骨架”
- 必须输出“Seedance 转译建议”
- 如果无法确定，不要编造，标记 uncertain

---

## 推荐工作流位置

参考视频
→ Video Case Analyzer
→ 分析 JSON / Markdown
→ Seedance Prompt Skill / Script Agent / Storyboard Agent
→ 生成视频

---

## 最终目标

让一个优秀参考视频，不只被“看懂”，而是被转化成：

- 一套可复用的传播结构
- 一套可迁移的视觉策略
- 一份可执行的 Seedance 生成依据
