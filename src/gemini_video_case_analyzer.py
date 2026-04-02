import argparse
import json
import os
import time
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
from shot_prompt_generator import generate_shot_prompts, render_shot_prompts_md, DEFAULT_MODEL


def run_gemini(video_path, prompt, model="gemini-2.0-flash"):
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
                 prompt_model: str | None = None):
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "analysis.json").write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (output_dir / "analysis.md").write_text(report_md, encoding="utf-8")
    (output_dir / "raw_output.txt").write_text(raw_text, encoding="utf-8")

    # 自动生成 Seedance 分镜提示词（通过 LLM）
    print(f"正在通过 LLM 生成 Seedance 分镜提示词（模型: {prompt_model or DEFAULT_MODEL}）...")
    try:
        shot_prompts = generate_shot_prompts(data, model=prompt_model)
        (output_dir / "shot_prompts.json").write_text(
            json.dumps(shot_prompts, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        (output_dir / "shot_prompts.md").write_text(
            render_shot_prompts_md(shot_prompts),
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
    parser.add_argument("--model", default="gemini-2.0-flash",
                        help="Gemini 视频分析模型")
    parser.add_argument("--prompt-model", default=None,
                        help="分镜提示词生成 LLM 模型（默认 anthropic/claude-sonnet-4.6，走 ZenMux）")

    args = parser.parse_args()

    user_prompt = build_user_prompt(
        goal=args.goal,
        target_platform=args.target_platform,
        output_depth=args.output_depth,
        focus=args.focus,
        variant_direction=args.variant_direction,
    )

    full_prompt = SYSTEM_PROMPT + "\n\n" + user_prompt
    raw_text = run_gemini(args.video, full_prompt, model=args.model)

    data, report_md = extract_first_json_block(raw_text)
    if not report_md:
        report_md = render_markdown_stub(data)

    save_outputs(Path(args.output_dir), data, report_md, raw_text,
                 prompt_model=args.prompt_model)
    print(f"Saved outputs to {args.output_dir}")


if __name__ == "__main__":
    main()
