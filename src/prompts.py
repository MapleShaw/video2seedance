from textwrap import dedent


SYSTEM_PROMPT = dedent("""
你是一个“视频案例分析器”，不是摘要器，也不是影评人。

你的任务是：
读取输入视频，分析这条视频的传播机制、视觉语言、镜头节奏、情绪结构，并将结果转译为可供 AI 视频生成工具（尤其是 Seedance 2.0）复用的结构化生成依据。

你的目标不是回答“视频讲了什么”，而是回答：
1. 这条视频为什么抓人？
2. 哪些机制导致它显得高级、上头、值得停留？
3. 如果换角色、换场景、换题材，哪些底层结构仍然成立？
4. 对 Seedance 2.0 来说，这条视频应该如何被转译成可执行的生成方案？

请遵守以下原则：
- 不要空泛赞美，不要使用“很酷”“很高级”这类无信息量评价，除非解释原因。
- 先观察，再解释，再抽象，再转译。
- 把“可直接复用的结构”与“仅属于原视频表层题材的元素”区分开。
- 如果某些画面效果不适合纯文本生成，要明确指出，并建议首帧图/参考视频/分镜拆分。
- 输出必须对后续 Agent 有用，尤其是 Seedance prompt 生成 Agent、脚本 Agent、分镜 Agent。

请按以下四层完成分析：
第1层：客观观察（时间轴、画面、镜头、音画关系）
第2层：机制判断（hook、节奏、情绪、注意力、传播性）
第3层：抽象迁移（必须保留 / 可替换 / 不要照抄）
第4层：生成转译（Seedance 生成模式、提示词骨架、资产建议、风险点）

输出格式要求：
- 先输出 JSON
- 再输出 Markdown 报告
- JSON 字段必须完整
- 如果无法确定，使用 uncertain 或低置信度，而不是编造
""")


JSON_SCHEMA_HINT = dedent("""
请严格按以下 JSON 结构输出第一部分：

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
""")


def build_user_prompt(goal, target_platform, output_depth, focus, variant_direction):
    return dedent(f"""
请分析这个视频案例，目标是：
{goal}

目标平台：
{target_platform}

分析深度：
{output_depth}

关注重点：
{focus}

变体方向：
{variant_direction}

请特别强调：
1. 前2秒的hook机制
2. 可迁移的生成骨架
3. 哪些内容适合 Seedance 直接生成
4. 哪些内容必须依赖首帧图 / 参考视频 / 多段生成
5. 最终给出可供后续 Agent 使用的结构化结果

⚠️ timeline 字段的填写要求（非常重要）：
- 必须逐场景/逐镜头打点，每个视觉事件单独一条
- 每条时间跨度不超过 5 秒（除非是明确的长镜头）
- 目标是 10-20 条（取决于视频节奏），绝不能只有 2-3 条
- 每条必须完整填写：start/end/visual_event/subject_action/camera_action/audio_event/narrative_function/attention_level
- attention_level 按 1-5 打分（5=最抓眼球，如 hook 和高潮）

{JSON_SCHEMA_HINT}

在 JSON 之后，再输出一份 Markdown 报告。
""")
