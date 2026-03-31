"""
shot_prompt_generator.py

从 analysis.json 自动生成 Seedance 2.0 分镜提示词。
如果检测到本地 Seedance skill，按其规范生成；否则使用内置规则。
"""

import json
import os
import textwrap
from pathlib import Path


# ─── Seedance Skill 检测 ────────────────────────────────────────────────────

SKILL_SEARCH_PATHS = [
    Path.home() / ".openclaw/workspace/skills/seedance-prompt/SKILL.md",
    Path("/usr/lib/node_modules/openclaw/skills/seedance-prompt/SKILL.md"),
]


def detect_seedance_skill() -> bool:
    for p in SKILL_SEARCH_PATHS:
        if p.exists():
            print(f"[shot_prompt_generator] 检测到 Seedance skill: {p}")
            return True
    print("[shot_prompt_generator] 未检测到 Seedance skill，使用内置规则")
    return False


# ─── 辅助工具 ───────────────────────────────────────────────────────────────

def _join(items, sep="、"):
    if not items:
        return ""
    return sep.join(items)


def _camera_cn(shot_types, movement_patterns):
    """把英文镜头类型 + 运动转成中文友好描述"""
    mapping = {
        "extreme close-up": "极端特写",
        "close-up": "特写",
        "medium shot": "中景",
        "wide shot": "宽景",
        "wide establishing shot": "定场宽景",
        "low angle": "低角度仰拍",
        "high angle": "俯拍",
        "over-the-shoulder": "过肩镜头",
        "aerial": "航拍",
        "pov": "主观视角",
        "static": "静止镜头",
        "slow tracking": "Slow Tracking缓慢跟移",
        "zoom-in": "Zoom In推近",
        "zoom-out": "Zoom Out拉远",
        "pan": "Pan摇移",
        "dolly": "Dolly推轨",
        "crane up": "Crane Up升镜",
        "orbit": "Orbit环绕",
        "handheld": "手持抖动",
    }
    parts = []
    for s in shot_types:
        parts.append(mapping.get(s.lower(), s))
    for m in movement_patterns:
        parts.append(mapping.get(m.lower(), m))
    return " + ".join(parts) if parts else "固定镜头"


def _style_prefix(visual_language: dict) -> str:
    """组装风格/色调前缀"""
    keywords = visual_language.get("style_keywords", [])
    palette = visual_language.get("palette", [])
    lighting = visual_language.get("lighting", [])
    style = _join(keywords, "、") or "Dark Fantasy"
    color = _join(palette[:3], "+") or "深红+黑"
    light = _join(lighting[:2], "+") or "高对比+体积雾"
    return f"{style}风格，{color}色调，{light}光影"


def _quality_anchor(visual_language: dict) -> str:
    """根据视觉语言判断品质锚定词"""
    keywords = " ".join(visual_language.get("style_keywords", [])).lower()
    if any(k in keywords for k in ["fantasy", "gothic", "cinematic", "dark"]):
        return "UE5渲染，电影级VFX，8K超清，"
    if any(k in keywords for k in ["cyber", "sci-fi", "future"]):
        return "UnrealEngine5渲染，工业光魔级VFX，杜比视界HDR，"
    return "电影级渲染，超高细节，"


# ─── 单镜头 Prompt 生成 ─────────────────────────────────────────────────────

def build_shot_prompt(
    shot: dict,
    visual_language: dict,
    camera_language: dict,
    style_prefix: str,
    quality_anchor: str,
    use_seedance_skill: bool,
    shot_index: int,
    total_shots: int,
) -> dict:
    """
    为单个 timeline 片段生成 Seedance prompt。
    返回 dict: {index, time_range, narrative_function, prompt, asset_hint}
    """
    start = shot.get("start", 0)
    end = shot.get("end", start + 3)
    duration = end - start
    # Seedance 单次上限 15s，超出截断提示
    capped = min(duration, 15)

    visual_event = shot.get("visual_event", "")
    subject_action = shot.get("subject_action", "")
    camera_action = shot.get("camera_action", "")
    narrative_fn = shot.get("narrative_function", "build")
    attention = shot.get("attention_level", 3)

    # 镜头语言
    shot_types = camera_language.get("shot_types", [])
    movement_patterns = camera_language.get("movement_patterns", [])
    camera_desc = _camera_cn([camera_action] if camera_action else shot_types[:2], movement_patterns[:1])

    # 环境
    env_traits = visual_language.get("environment_traits", [])
    env_desc = _join(env_traits[:2]) or "迷雾场景"

    # 纹理/特效
    texture_fx = visual_language.get("texture_fx", [])
    fx_desc = _join(texture_fx[:2])

    # 主体设计
    subject_traits = visual_language.get("subject_design_traits", [])
    subject_desc = _join(subject_traits[:3])

    # ── 构建 prompt ──
    if use_seedance_skill:
        # 按 Seedance skill 史诗/大制作结构
        # hook 镜头用特别强调的开场
        if narrative_fn == "hook":
            prompt = (
                f"{capped}秒，{quality_anchor}{style_prefix}，\n"
                f"全片统一的体积雾弥散效果，高饱和点缀色彩策略，\n"
                f"0-{capped}秒：{visual_event}，{subject_action}，"
                f"{camera_desc}，{env_desc}背景，"
                f"{'，'.join(subject_traits[:2]) + '，' if subject_traits else ''}"
                f"{'，'.join(texture_fx[:2]) + '，' if texture_fx else ''}"
                f"前2秒静止对峙制造张力，镜头缓慢推近；\n"
                f"光影：高对比逆光+体积雾弥散（光源层），"
                f"雾气柔化高光同时强化阴影对比（光行为层），"
                f"{'，'.join(visual_language.get('palette', [])[:3])}（色调层）。\n"
                f"禁止：任何文字、字幕、LOGO或水印"
            )
        elif narrative_fn in ("payoff", "ending"):
            prompt = (
                f"{capped}秒，{quality_anchor}{style_prefix}，\n"
                f"高潮叙事收束段落，情绪强度最高点，\n"
                f"0-{capped}秒：{visual_event}，{subject_action}，"
                f"{camera_desc}，{env_desc}，"
                f"法术/符咒/粒子爆发效果，慢镜头120帧/秒，\n"
                f"镜头轻微抖动增强冲击感，雾粒粘镜效果；\n"
                f"光影：爆发光源+环境色（光源层），光行为：丁达尔效应（光行为层），"
                f"{'，'.join(visual_language.get('palette', [])[:2])}高对比（色调层）。\n"
                f"收束：暗角+胶片颗粒，全程高张力，无冗余画面。\n"
                f"禁止：任何文字、字幕、LOGO或水印"
            )
        else:
            prompt = (
                f"{capped}秒，{style_prefix}，\n"
                f"0-{capped}秒：{visual_event}，{subject_action}，"
                f"{camera_desc}，{env_desc}，"
                f"{fx_desc + '，' if fx_desc else ''}"
                f"体积雾弥散，{'，'.join(visual_language.get('lighting', [])[:2])}；\n"
                f"禁止：任何文字、字幕、LOGO或水印"
            )
    else:
        # 内置规则（简化版）
        prompt = (
            f"{capped}秒视频，{style_prefix}，"
            f"{visual_event}，{subject_action}，"
            f"镜头：{camera_desc}，场景：{env_desc}，"
            f"{'特效：' + fx_desc + '，' if fx_desc else ''}"
            f"高细节，电影感"
        )

    # 素材建议
    asset_hint = []
    if narrative_fn == "hook" or attention >= 4:
        asset_hint.append("建议准备首帧参考图（@图片1）以锁定角色外貌")
    if subject_traits:
        asset_hint.append(f"角色需要：{_join(subject_traits[:2])}")
    if duration > 15:
        asset_hint.append(f"⚠️ 本段时长{duration}s，超出单次生成上限15s，建议拆为{duration // 15 + 1}段")

    return {
        "index": shot_index + 1,
        "time_range": f"{start}s-{end}s",
        "duration_seconds": duration,
        "narrative_function": narrative_fn,
        "attention_level": attention,
        "prompt": prompt.strip(),
        "asset_hints": asset_hint,
    }


# ─── 完整分镜计划生成 ───────────────────────────────────────────────────────

def generate_shot_prompts(analysis_data: dict) -> dict:
    """
    输入：analysis.json 的 dict
    输出：shot_prompts dict，包含 metadata + shots 列表
    """
    use_skill = detect_seedance_skill()

    visual_language = analysis_data.get("visual_language", {})
    camera_language = analysis_data.get("camera_language", {})
    timeline = analysis_data.get("timeline", [])
    rhythm = analysis_data.get("rhythm_structure", {})
    meta = analysis_data.get("meta", {})
    seedance = analysis_data.get("seedance_translation", {})
    transferable = analysis_data.get("transferable_pattern", {})
    next_steps = analysis_data.get("next_step_assets", {})

    style_prefix = _style_prefix(visual_language)
    quality_anchor = _quality_anchor(visual_language)

    shots = []
    for i, shot in enumerate(timeline):
        shot_prompt = build_shot_prompt(
            shot=shot,
            visual_language=visual_language,
            camera_language=camera_language,
            style_prefix=style_prefix,
            quality_anchor=quality_anchor,
            use_seedance_skill=use_skill,
            shot_index=i,
            total_shots=len(timeline),
        )
        shots.append(shot_prompt)

    # 汇总变体建议
    variants = next_steps.get("variants", [])
    variant_notes = []
    for v in variants:
        variant_notes.append({
            "name": v.get("name"),
            "direction": v.get("direction"),
            "what_changes": v.get("what_changes", []),
            "what_stays": v.get("what_stays", []),
            "note": f"沿用「{_join(v.get('what_stays', []))}」，替换「{_join(v.get('what_changes', []))}」",
        })

    return {
        "metadata": {
            "source_title": meta.get("title", "untitled"),
            "total_duration_seconds": meta.get("duration_seconds", 0),
            "aspect_ratio": meta.get("aspect_ratio", "9:16"),
            "seedance_skill_detected": use_skill,
            "recommended_mode": seedance.get("recommended_mode", "multi-stage"),
            "abstract_pattern": transferable.get("abstract_pattern", ""),
            "risk_points": seedance.get("risk_points", []),
            "shot_count": len(shots),
        },
        "shots": shots,
        "variants": variant_notes,
        "workflow_note": (
            "生成顺序建议：① 准备首帧参考图（用于 hook 段） "
            "→ ② 按 shots 列表逐条在即梦生成 3-5s 片段 "
            "→ ③ 按 rhythm_structure.pattern 节奏卡点剪辑拼接"
        ),
    }
    


# ─── Markdown 报告渲染 ──────────────────────────────────────────────────────

def render_shot_prompts_md(shot_prompts: dict) -> str:
    meta = shot_prompts["metadata"]
    workflow_note = shot_prompts.get("workflow_note", "")
    lines = [
        f"# 分镜提示词计划：{meta['source_title']}",
        "",
        f"> **Seedance Skill**：{'✅ 已检测到，按官方规范生成' if meta['seedance_skill_detected'] else '❌ 未检测到，使用内置规则'}",
        f"> **推荐模式**：{meta['recommended_mode']}",
        f"> **抽象骨架**：{meta['abstract_pattern']}",
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

    for shot in shot_prompts["shots"]:
        lines += [
            f"### Shot {shot['index']}  `{shot['time_range']}`  `{shot['narrative_function']}`  注意力:{shot['attention_level']}/5",
            "",
            "```",
            shot["prompt"],
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
                f"### {v['name']} — {v['direction']}",
                "",
                v["note"],
                "",
            ]

    return "\n".join(lines)


# ─── CLI 入口 ───────────────────────────────────────────────────────────────

def main():
    import argparse

    parser = argparse.ArgumentParser(description="从 analysis.json 生成 Seedance 分镜提示词")
    parser.add_argument("analysis_json", help="analysis.json 路径")
    parser.add_argument("--output-dir", default=None, help="输出目录（默认与 JSON 同目录）")
    args = parser.parse_args()

    json_path = Path(args.analysis_json)
    output_dir = Path(args.output_dir) if args.output_dir else json_path.parent

    with open(json_path, encoding="utf-8") as f:
        data = json.load(f)

    shot_prompts = generate_shot_prompts(data)

    # 保存 JSON
    out_json = output_dir / "shot_prompts.json"
    out_json.write_text(json.dumps(shot_prompts, ensure_ascii=False, indent=2), encoding="utf-8")

    # 保存 Markdown
    out_md = output_dir / "shot_prompts.md"
    out_md.write_text(render_shot_prompts_md(shot_prompts), encoding="utf-8")

    print(f"✅ 生成完成：{out_json}")
    print(f"✅ 生成完成：{out_md}")
    print(f"   共 {shot_prompts['metadata']['shot_count']} 个分镜 prompt")


if __name__ == "__main__":
    main()
