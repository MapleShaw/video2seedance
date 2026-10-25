import argparse
import json
import os
import subprocess
import time
from math import gcd
from pathlib import Path

# 自动加载项目根目录 .env
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent.parent / ".env")
except ImportError:
    pass

from google import genai
from google.genai import types

from prompts import SYSTEM_PROMPT, build_user_prompt
from utils import extract_first_json_block
from formatter import render_markdown_stub
from shot_prompt_generator import generate_shot_prompts, render_prompts_md, DEFAULT_MODEL


def detect_aspect_ratio(video_path: str) -> str | None:
    """用 ffprobe 读取视频真实分辨率，返回简化比例字符串（如 '16:9'）。"""
    try:
        result = subprocess.run(
            [
                "ffprobe", "-v", "error",
                "-select_streams", "v:0",
                "-show_entries", "stream=width,height",
                "-of", "json",
                str(video_path),
            ],
            capture_output=True, text=True, timeout=10,
        )
        info = json.loads(result.stdout)
        stream = info["streams"][0]
        w, h = int(stream["width"]), int(stream["height"])
        g = gcd(w, h)
        ratio = f"{w // g}:{h // g}"
        # 常见比例归一化
        common = {"16:9", "9:16", "4:3", "3:4", "1:1", "21:9", "9:21", "2:1", "1:2"}
        if ratio in common:
            return ratio
        # 尝试近似匹配
        r = w / h
        if abs(r - 16/9) < 0.05:
            return "16:9"
        elif abs(r - 9/16) < 0.05:
            return "9:16"
        elif abs(r - 4/3) < 0.05:
            return "4:3"
        elif abs(r - 1) < 0.05:
            return "1:1"
        return ratio
    except Exception as e:
        print(f"⚠️ ffprobe 检测画幅比失败（{e}），将使用 Gemini 分析结果")
        return None


def run_gemini(video_path, prompt, model="gemini-2.5-flash"):
    """
    使用 google-genai SDK 上传视频并分析。
    需要设置环境变量 GEMINI_API_KEY。
    """
    api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        raise RuntimeError("请设置环境变量 GEMINI_API_KEY")

    # 视频上传+分析耗时较长，通过 client_args 注入 httpx timeout（覆盖代理默认超时）
    # timeout 各阶段单独设置：write/read 各 10 分钟
    client = genai.Client(
        api_key=api_key,
        http_options=types.HttpOptions(
            client_args={
                "timeout": {
                    "connect": 30.0,
                    "write": 600.0,
                    "read": 600.0,
                    "pool": 10.0,
                }
            }
        ),
    )

    video_file_path = Path(video_path)
    print(f"正在上传视频: {video_file_path.name} ...")
    video_file = client.files.upload(file=str(video_file_path))

    # 等待文件处理完成
    print("等待 Gemini 处理视频...")
    while video_file.state.name == "PROCESSING":
        time.sleep(5)
        video_file = client.files.get(name=video_file.name)

    if video_file.state.name == "FAILED":
        raise RuntimeError(f"视频处理失败: {video_file.state.name}")

    print(f"视频处理完成，开始分析（模型: {model}）...")
    response = client.models.generate_content(
        model=model,
        contents=[
            types.Part.from_uri(file_uri=video_file.uri, mime_type=video_file.mime_type),
            prompt,
        ],
    )

    # 清理上传的文件
    try:
        client.files.delete(name=video_file.name)
    except Exception:
        pass

    return response.text


def save_outputs(output_dir: Path, data: dict, report_md: str, raw_text: str,
                 prompt_model: str | None = None,
                 max_shots: int | None = None,
                 style_hint: str | None = None,
                 image_model: str = "nanobanana",
                 mode: str = "auto"):
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "analysis.json").write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (output_dir / "analysis.md").write_text(report_md, encoding="utf-8")
    (output_dir / "raw_output.txt").write_text(raw_text, encoding="utf-8")

    # 截取 timeline（快速测试模式）
    gen_data = data
    if max_shots:
        import copy
        gen_data = copy.deepcopy(data)
        original_count = len(gen_data.get("timeline", []))
        gen_data["timeline"] = gen_data.get("timeline", [])[:max_shots]
        print(f"⚡ 快速测试模式：只处理前 {max_shots} 条 timeline（共 {original_count} 条）")

    # 自动生成 Seedance 提示词（通过 LLM）
    print(f"正在通过 LLM 生成 Seedance 提示词（模型: {prompt_model or DEFAULT_MODEL}，模式: {mode}）...")
    try:
        shot_prompts = generate_shot_prompts(
            gen_data, model=prompt_model,
            style_hint=style_hint, image_model=image_model,
            mode=mode,
        )
        (output_dir / "shot_prompts.json").write_text(
            json.dumps(shot_prompts, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        (output_dir / "prompts.md").write_text(
            render_prompts_md(shot_prompts),
            encoding="utf-8",
        )
        shot_count = shot_prompts.get("metadata", {}).get("shot_count", len(shot_prompts.get("shots", [])))
        skill_used = shot_prompts.get("metadata", {}).get("seedance_skill_detected", False)
        print(f"✅ 分镜提示词已生成：{shot_count} 个镜头，Seedance skill: {'✅ 已使用' if skill_used else '⚠️ 未检测到'}")
    except Exception as e:
        print(f"⚠️  分镜提示词生成失败（不影响主分析输出）：{e}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("video")
    parser.add_argument("--goal", default="提炼这条视频的传播机制与 Seedance 可迁移骨架")
    parser.add_argument("--target-platform", default="seedance")
    parser.add_argument("--output-depth", default="standard")
    parser.add_argument("--focus", default="hook,rhythm,visual_style,seedance_translation")
    parser.add_argument("--variant-direction", default="保留核心机制，但允许换角色、换题材、换世界观")
    parser.add_argument("--output-dir", default="./output")
    parser.add_argument("--model", default="gemini-2.5-flash",
                        help="Gemini 视频分析模型（仅 --analyzer gemini 时生效）")
    parser.add_argument("--analyzer", default="gemini",
                        choices=["gemini", "frames"],
                        help="视频分析渠道：gemini=直接上传视频给 Gemini；"
                             "frames=本地 ffmpeg 抽关键帧后用多模态 LLM 分析（默认 gemini）")
    parser.add_argument("--vision-model", default=None,
                        help="frames 渠道用的多模态 LLM（走 ZenMux，默认 anthropic/claude-sonnet-4.6，"
                             "可选 openai/gpt-5.2、google/gemini-3-pro-preview 等）")
    parser.add_argument("--max-frames", type=int, default=16,
                        help="frames 渠道抽取的关键帧数量上限（默认 16）")
    parser.add_argument("--frame-method", default="interval",
                        choices=["interval", "scene"],
                        help="frames 抽帧策略：interval=按时长均匀抽帧；scene=场景切换检测（默认 interval）")
    parser.add_argument("--prompt-model", default=None,
                        help="分镜提示词生成 LLM 模型（默认 anthropic/claude-sonnet-4.6，走 ZenMux）")
    parser.add_argument("--realism-level", default=None,
                        choices=["photorealistic", "semi-realistic", "3d-render", "stylized", "anime", "abstract"],
                        help="强制覆盖 Gemini 分析出的 realism_level（当 Gemini 判断不准时使用）")
    parser.add_argument("--max-shots", type=int, default=None,
                        help="二阶段只处理前 N 条 timeline（快速测试用，省 token）")
    parser.add_argument("--style-hint", default=None,
                        help="用自然语言描述视频风格，透传给二阶段（如 '暗黑东方仙侠真人实拍，中式五官'）")
    parser.add_argument("--image-model", default="nanobanana",
                        choices=["nanobanana", "seedance"],
                        help="角色参考图的目标图片生成平台（默认 nanobanana）")
    parser.add_argument("--aspect-ratio", default=None,
                        help="强制覆盖视频画幅比（如 16:9, 9:16, 1:1），不指定则用 ffprobe 自动检测")
    parser.add_argument("--mode", default="auto",
                        choices=["auto", "single", "storyboard"],
                        help="生成模式：auto=自动判断，single=强制单prompt，storyboard=强制分镜（默认 auto）")
    parser.add_argument("--no-report", action="store_true",
                        help="不生成 report.html 可视化报告")

    args = parser.parse_args()

    user_prompt = build_user_prompt(
        goal=args.goal,
        target_platform=args.target_platform,
        output_depth=args.output_depth,
        focus=args.focus,
        variant_direction=args.variant_direction,
    )

    if args.analyzer == "frames":
        from frame_analyzer import analyze_video_via_frames
        print(f"🎞️ 分析渠道：frames（本地 ffmpeg 抽帧 + 多模态 LLM）")
        raw_text = analyze_video_via_frames(
            args.video,
            system_prompt=SYSTEM_PROMPT,
            user_prompt=user_prompt,
            model=args.vision_model,
            max_frames=args.max_frames,
            method=args.frame_method,
        )
    else:
        print(f"🎬 分析渠道：gemini（直接上传视频，模型 {args.model}）")
        full_prompt = SYSTEM_PROMPT + "\n\n" + user_prompt
        raw_text = run_gemini(args.video, full_prompt, model=args.model)

    data, report_md = extract_first_json_block(raw_text)
    if not report_md:
        report_md = render_markdown_stub(data)

    # 强制覆盖 realism_level
    if args.realism_level:
        old_level = data.get("visual_language", {}).get("realism_level", "未设置")
        data.setdefault("visual_language", {})["realism_level"] = args.realism_level
        print(f"⚠️ 强制覆盖 realism_level: {old_level} → {args.realism_level}")

    # 画幅比：优先 CLI 参数 > ffprobe 自动检测 > Gemini 分析结果
    gemini_ratio = data.get("meta", {}).get("aspect_ratio", "未设置")
    if args.aspect_ratio:
        data.setdefault("meta", {})["aspect_ratio"] = args.aspect_ratio
        print(f"⚠️ 强制覆盖 aspect_ratio: {gemini_ratio} → {args.aspect_ratio}")
    else:
        detected_ratio = detect_aspect_ratio(args.video)
        if detected_ratio and detected_ratio != gemini_ratio:
            data.setdefault("meta", {})["aspect_ratio"] = detected_ratio
            print(f"📐 ffprobe 检测画幅比: {detected_ratio}（Gemini 判断为 {gemini_ratio}，已自动修正）")
        elif detected_ratio:
            print(f"📐 画幅比确认: {detected_ratio}")

    save_outputs(Path(args.output_dir), data, report_md, raw_text,
                 prompt_model=args.prompt_model,
                 max_shots=args.max_shots,
                 style_hint=args.style_hint,
                 image_model=args.image_model,
                 mode=args.mode)
    print(f"Saved outputs to {args.output_dir}")

    if not args.no_report:
        from report_builder import build_report, check_summary
        try:
            path, doc = build_report(Path(args.output_dir), video=Path(args.video))
            print(f"📊 可视化报告：{path}（{check_summary(doc)}）")
        except Exception as e:
            print(f"⚠️  可视化报告生成失败（不影响主分析输出）：{e}")


if __name__ == "__main__":
    main()
