"""
shot_prompt_generator.py

从 analysis.json + Seedance SKILL.md 生成高质量分镜提示词。
通过 LLM（默认走 ZenMux OpenAI 兼容接口）理解分析结果和 skill 规范后智能生成，
不再做死模板拼接。

环境变量:
  ZENMUX_API_KEY  - ZenMux API Key（必需）
  ZENMUX_BASE_URL - ZenMux base URL（可选，默认 https://zenmux.ai/api/v1）
  SEEDANCE_MODEL  - 模型名（可选，默认 anthropic/claude-sonnet-4.6）
"""

import json
import os
import sys
from pathlib import Path
from textwrap import dedent


# ─── Seedance Skill 检测 & 读取 ─────────────────────────────────────────────

SKILL_SEARCH_PATHS = [
    Path.home() / ".openclaw/workspace/skills/seedance-prompt/SKILL.md",
    Path("/usr/lib/node_modules/openclaw/skills/seedance-prompt/SKILL.md"),
]


def load_seedance_skill() -> str | None:
    """尝试加载 SKILL.md 内容。找到返回文本，找不到返回 None。"""
    for p in SKILL_SEARCH_PATHS:
        if p.exists():
            print(f"[shot_prompt_generator] ✅ 检测到 Seedance skill: {p}")
            return p.read_text(encoding="utf-8")
    # 也检查项目自带的 SKILL.md
    local_skill = Path(__file__).parent.parent / "SKILL.md"
    if local_skill.exists():
        print(f"[shot_prompt_generator] ✅ 检测到项目内 SKILL.md: {local_skill}")
        return local_skill.read_text(encoding="utf-8")
    print("[shot_prompt_generator] ⚠️ 未检测到 Seedance SKILL.md，LLM 将使用内置知识生成")
    return None


# ─── LLM 调用 ───────────────────────────────────────────────────────────────

DEFAULT_BASE_URL = "https://zenmux.ai/api/v1"
DEFAULT_MODEL = "anthropic/claude-sonnet-4.6"


def call_llm(
    system_prompt: str,
    user_prompt: str,
    model: str | None = None,
    base_url: str | None = None,
    api_key: str | None = None,
) -> str:
    """调用 OpenAI 兼容 API（默认 ZenMux），返回文本响应。"""
    try:
        from openai import OpenAI
    except ImportError:
        print("❌ 需要安装 openai: pip install openai", file=sys.stderr)
        sys.exit(1)

    _api_key = api_key or os.environ.get("ZENMUX_API_KEY")
    if not _api_key:
        print("❌ 请设置环境变量 ZENMUX_API_KEY", file=sys.stderr)
        sys.exit(1)

    _base_url = base_url or os.environ.get("ZENMUX_BASE_URL", DEFAULT_BASE_URL)
    _model = model or os.environ.get("SEEDANCE_MODEL", DEFAULT_MODEL)

    client = OpenAI(base_url=_base_url, api_key=_api_key)

    print(f"[shot_prompt_generator] 调用 LLM: {_model} @ {_base_url}")
    response = client.chat.completions.create(
        model=_model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        max_tokens=12000,
        temperature=0.7,
    )
    return response.choices[0].message.content


# ─── Prompt 构建 ────────────────────────────────────────────────────────────

def build_system_prompt(skill_content: str | None) -> str:
    """构建 system prompt，包含 SKILL.md 规范（如果有的话）。"""
    base = dedent("""\
    你是 Seedance 2.0（即梦）分镜提示词专家。

    你的任务：
    根据视频分析结果（JSON），为每个 timeline 分镜生成可直接复制到即梦平台使用的中文提示词。

    核心要求：
    1. 所有提示词必须使用中文
    2. 每个 shot 的 prompt 必须是完整可用的——直接粘贴到即梦就能生成
    3. 根据 narrative_function 和 attention_level 调整提示词的强度和复杂度：
       - hook（开场）：最强视觉冲击，前2秒定生死
       - payoff/ending（高潮/结尾）：情绪最高点，用史诗结构
       - build/setup/twist（中段）：服务叙事推进，保持节奏
    4. 运镜用中英混合描述（如"Slow Crane Up缓慢升镜"），效果更好
    5. 每个 prompt 末尾加"禁止：任何文字、字幕、LOGO或水印"
    6. 单次生成上限15秒，超出的要标注拆分建议
    7. 根据视觉风格自动匹配品质锚定词（UE5渲染/电影级/etc.）

    输出格式：
    严格输出一个 JSON 对象，结构如下（不要输出其他内容，不要 markdown code fence）：
    {
      "metadata": {
        "source_title": "string",
        "total_duration_seconds": number,
        "aspect_ratio": "string",
        "seedance_skill_used": boolean,
        "recommended_mode": "string",
        "abstract_pattern": "string",
        "risk_points": ["string"],
        "shot_count": number
      },
      "shots": [
        {
          "index": 1,
          "time_range": "0s-3s",
          "duration_seconds": 3,
          "narrative_function": "hook",
          "attention_level": 5,
          "prompt": "完整的 Seedance 提示词",
          "asset_hints": ["素材建议"]
        }
      ],
      "variants": [
        {
          "name": "变体名",
          "direction": "方向",
          "what_changes": [],
          "what_stays": [],
          "note": "说明"
        }
      ],
      "workflow_note": "生成顺序建议"
    }
    """)

    if skill_content:
        return (
            base
            + "\n\n---\n\n"
            + "以下是 Seedance 2.0 官方提示词规范，请严格遵守其中的结构模板、运镜体系、"
            + "@引用规则、质量自检 Checklist 等要求：\n\n"
            + skill_content
        )
    else:
        return (
            base
            + "\n\n注意：未提供 Seedance SKILL.md 规范文件，请根据你对 Seedance 2.0 的了解生成。"
        )


def build_user_prompt(analysis_data: dict) -> str:
    """将 analysis.json 格式化为 user prompt。"""
    analysis_json = json.dumps(analysis_data, ensure_ascii=False, indent=2)
    return dedent(f"""\
    请基于以下视频分析结果，为每个 timeline 分镜生成 Seedance 2.0 提示词。

    分析结果：
    {analysis_json}

    要求：
    1. 为 timeline 中的每个条目生成独立可用的提示词
    2. hook 段和 payoff 段使用史诗/大制作结构（品质锚定 + 大气连贯声明 + 光影三层）
    3. 普通段使用时间戳分镜法或基础结构
    4. 每个 prompt 都要融入 visual_language 中的风格/色调/光影信息
    5. 根据 camera_language 选择合适的运镜组合
    6. 标注需要首帧图/参考素材的镜头
    7. 超过15秒的段落标注拆分建议
    8. 保留 transferable_pattern 中"必须保留"的元素
    9. 生成2-3个变体方向建议
    """)


# ─── 结果解析 ────────────────────────────────────────────────────────────────

def parse_llm_response(response_text: str) -> dict:
    """从 LLM 响应中提取 JSON。"""
    text = response_text.strip()

    # 去掉可能的 markdown code fence
    if text.startswith("```"):
        # 找到第一个换行后的内容
        first_nl = text.index("\n")
        last_fence = text.rfind("```")
        if last_fence > first_nl:
            text = text[first_nl + 1:last_fence].strip()

    # 找 JSON 对象
    json_start = text.find("{")
    if json_start == -1:
        raise ValueError("LLM 响应中没有找到 JSON 对象")

    brace_count = 0
    json_end = None
    for i, ch in enumerate(text[json_start:], start=json_start):
        if ch == "{":
            brace_count += 1
        elif ch == "}":
            brace_count -= 1
            if brace_count == 0:
                json_end = i + 1
                break

    if json_end is None:
        raise ValueError("JSON 对象不完整")

    return json.loads(text[json_start:json_end])


# ─── 主入口（兼容原有调用方式）────────────────────────────────────────────────

def generate_shot_prompts(
    analysis_data: dict,
    model: str | None = None,
    base_url: str | None = None,
    api_key: str | None = None,
) -> dict:
    """
    输入：analysis.json 的 dict
    输出：shot_prompts dict（结构同原版，向后兼容）

    新增可选参数：model, base_url, api_key（均可通过环境变量配置）
    """
    skill_content = load_seedance_skill()
    system_prompt = build_system_prompt(skill_content)
    user_prompt = build_user_prompt(analysis_data)

    response_text = call_llm(
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        model=model,
        base_url=base_url,
        api_key=api_key,
    )

    result = parse_llm_response(response_text)

    # 确保 metadata 中有 seedance_skill_detected 字段（向后兼容）
    if "metadata" in result:
        result["metadata"]["seedance_skill_detected"] = skill_content is not None
        # 兼容旧字段名
        if "seedance_skill_used" in result["metadata"]:
            del result["metadata"]["seedance_skill_used"]

    return result


# ─── Markdown 报告渲染（保持不变）──────────────────────────────────────────────

def render_shot_prompts_md(shot_prompts: dict) -> str:
    meta = shot_prompts.get("metadata", {})
    workflow_note = shot_prompts.get("workflow_note", "")
    lines = [
        f"# 分镜提示词计划：{meta.get('source_title', 'untitled')}",
        "",
        f"> **Seedance Skill**：{'✅ 已使用官方规范' if meta.get('seedance_skill_detected') else '⚠️ 未检测到规范文件，基于 LLM 内置知识生成'}",
        f"> **推荐模式**：{meta.get('recommended_mode', 'N/A')}",
        f"> **抽象骨架**：{meta.get('abstract_pattern', 'N/A')}",
        "",
        "---",
        "",
        "## 工作流说明",
        "",
        workflow_note,
        "",
    ]

    if meta.get("risk_points"):
        lines += ["## ⚠️ 风险点", ""]
        for r in meta["risk_points"]:
            lines.append(f"- {r}")
        lines.append("")

    lines += ["---", "", "## 分镜提示词", ""]

    for shot in shot_prompts.get("shots", []):
        lines += [
            f"### Shot {shot.get('index', '?')}  `{shot.get('time_range', '?')}`  `{shot.get('narrative_function', '?')}`  注意力:{shot.get('attention_level', '?')}/5",
            "",
            "```",
            shot.get("prompt", ""),
            "```",
            "",
        ]
        if shot.get("asset_hints"):
            for hint in shot["asset_hints"]:
                lines.append(f"> 💡 {hint}")
            lines.append("")

    if shot_prompts.get("variants"):
        lines += ["---", "", "## 变体方向", ""]
        for v in shot_prompts["variants"]:
            lines += [
                f"### {v.get('name', '?')} — {v.get('direction', '?')}",
                "",
                v.get("note", ""),
                "",
            ]

    return "\n".join(lines)


# ─── CLI 入口 ───────────────────────────────────────────────────────────────

def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="从 analysis.json 生成 Seedance 分镜提示词（通过 LLM）"
    )
    parser.add_argument("analysis_json", help="analysis.json 路径")
    parser.add_argument("--output-dir", default=None, help="输出目录（默认与 JSON 同目录）")
    parser.add_argument(
        "--model",
        default=None,
        help=f"LLM 模型（默认 {DEFAULT_MODEL}，可选 anthropic/claude-opus-4.6, openai/gpt-5.2 等）",
    )
    parser.add_argument(
        "--base-url",
        default=None,
        help=f"API base URL（默认 {DEFAULT_BASE_URL}）",
    )
    args = parser.parse_args()

    json_path = Path(args.analysis_json)
    output_dir = Path(args.output_dir) if args.output_dir else json_path.parent

    with open(json_path, encoding="utf-8") as f:
        data = json.load(f)

    print(f"[shot_prompt_generator] 分析文件：{json_path}")
    print(f"[shot_prompt_generator] Timeline 条目数：{len(data.get('timeline', []))}")

    shot_prompts = generate_shot_prompts(
        data,
        model=args.model,
        base_url=args.base_url,
    )

    # 保存 JSON
    output_dir.mkdir(parents=True, exist_ok=True)
    out_json = output_dir / "shot_prompts.json"
    out_json.write_text(json.dumps(shot_prompts, ensure_ascii=False, indent=2), encoding="utf-8")

    # 保存 Markdown
    out_md = output_dir / "shot_prompts.md"
    out_md.write_text(render_shot_prompts_md(shot_prompts), encoding="utf-8")

    shot_count = shot_prompts.get("metadata", {}).get("shot_count", len(shot_prompts.get("shots", [])))
    skill_used = shot_prompts.get("metadata", {}).get("seedance_skill_detected", False)
    print(f"✅ 生成完成：{out_json}")
    print(f"✅ 生成完成：{out_md}")
    print(f"   共 {shot_count} 个分镜 prompt，Seedance skill: {'✅ 已使用' if skill_used else '⚠️ 未检测到'}")


if __name__ == "__main__":
    main()
