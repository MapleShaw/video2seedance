import argparse
import json
import os
import time
from pathlib import Path

import google.generativeai as genai

from prompts import SYSTEM_PROMPT, build_user_prompt
from utils import extract_first_json_block
from formatter import render_markdown_stub


def run_gemini(video_path, prompt):
    """
    使用 Google Generative AI SDK 上传视频并分析。
    需要设置环境变量 GEMINI_API_KEY。
    """
    api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        raise RuntimeError("请设置环境变量 GEMINI_API_KEY")

    genai.configure(api_key=api_key)

    video_file_path = Path(video_path)
    print(f"正在上传视频: {video_file_path.name} ...")
    video_file = genai.upload_file(path=str(video_file_path))

    # 等待文件处理完成
    print("等待 Gemini 处理视频...")
    while video_file.state.name == "PROCESSING":
        time.sleep(5)
        video_file = genai.get_file(video_file.name)

    if video_file.state.name == "FAILED":
        raise RuntimeError(f"视频处理失败: {video_file.state.name}")

    print("视频处理完成，开始分析...")
    model = genai.GenerativeModel(model_name="gemini-2.0-flash")
    response = model.generate_content([video_file, prompt])

    # 清理上传的文件
    try:
        genai.delete_file(video_file.name)
    except Exception:
        pass

    return response.text


def save_outputs(output_dir: Path, data: dict, report_md: str, raw_text: str):
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "analysis.json").write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (output_dir / "analysis.md").write_text(report_md, encoding="utf-8")
    (output_dir / "raw_output.txt").write_text(raw_text, encoding="utf-8")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("video")
    parser.add_argument("--goal", default="提炼这条视频的传播机制与 Seedance 可迁移骨架")
    parser.add_argument("--target-platform", default="seedance")
    parser.add_argument("--output-depth", default="standard")
    parser.add_argument("--focus", default="hook,rhythm,visual_style,seedance_translation")
    parser.add_argument("--variant-direction", default="保留核心机制，但允许换角色、换题材、换世界观")
    parser.add_argument("--output-dir", default="./output")

    args = parser.parse_args()

    user_prompt = build_user_prompt(
        goal=args.goal,
        target_platform=args.target_platform,
        output_depth=args.output_depth,
        focus=args.focus,
        variant_direction=args.variant_direction,
    )

    full_prompt = SYSTEM_PROMPT + "\n\n" + user_prompt
    raw_text = run_gemini(args.video, full_prompt)

    data, report_md = extract_first_json_block(raw_text)
    if not report_md:
        report_md = render_markdown_stub(data)

    save_outputs(Path(args.output_dir), data, report_md, raw_text)
    print(f"Saved outputs to {args.output_dir}")


if __name__ == "__main__":
    main()
