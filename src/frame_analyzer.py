"""
frame_analyzer.py

视频分析的「本地切帧 + 多模态 LLM」渠道（Gemini 之外的另一条路）。

流程：ffmpeg 抽取关键帧 → base64 → 通过 ZenMux 调用支持 vision 的 LLM
（GPT / Claude / Gemini 均可）分析这组关键帧。

输出与 run_gemini 对齐：返回 raw_text（内含 JSON + Markdown），
下游 extract_first_json_block / save_outputs 完全复用，无需改动。

环境变量：
  ZENMUX_API_KEY  - 必需
  ZENMUX_BASE_URL - 可选，默认 https://zenmux.ai/api/v1
"""

import base64
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

# 自动加载项目根目录 .env
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent.parent / ".env")
except ImportError:
    pass

import os

DEFAULT_BASE_URL = "https://zenmux.ai/api/v1"
# 默认用支持 vision 的模型；可通过 --vision-model 切换（gpt/claude/gemini 均可）
DEFAULT_VISION_MODEL = "anthropic/claude-sonnet-4.6"


def get_video_duration(video_path: str) -> float:
    """用 ffprobe 获取视频时长（秒）。失败返回 0.0。"""
    try:
        result = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", str(video_path)],
            capture_output=True, text=True, timeout=30,
        )
        return float(result.stdout.strip())
    except Exception:
        return 0.0


def extract_keyframes(video_path, out_dir, max_frames=16, method="interval"):
    """
    用 ffmpeg 抽帧。返回 (frames, duration)，
    frames 为 [(timestamp_seconds, frame_path), ...]。

    method:
      - interval: 按时长均匀抽 max_frames 帧（默认，覆盖全片）
      - scene:    场景切换检测抽帧（突出画面变化点，上限 max_frames）
    """
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    duration = get_video_duration(video_path)

    if method == "scene":
        # 场景检测：scene 分数 > 0.3 视为切换点；showinfo 记录真实 PTS
        vf = "select='gt(scene\\,0.3)',showinfo,scale=640:-1"
        cmd = ["ffmpeg", "-y", "-i", str(video_path), "-vf", vf,
               "-fps_mode", "vfr", "-frames:v", str(max_frames),
               str(out_dir / "frame_%04d.jpg")]
    else:
        # interval 均匀抽帧：覆盖从片头到结束前 0.05 秒；showinfo 记录真实 PTS
        if duration <= 0:
            duration = float(max_frames)
        if max_frames <= 1:
            fps_val = 1.0 / max(duration, 0.001)
        else:
            sampling_span = max(duration - 0.05, 0.001)
            fps_val = (max_frames - 1) / sampling_span
        vf = f"fps=fps={fps_val}:round=up:eof_action=pass,showinfo,scale=640:-1"
        cmd = ["ffmpeg", "-y", "-i", str(video_path), "-vf", vf,
               "-frames:v", str(max_frames),
               str(out_dir / "frame_%04d.jpg")]

    completed = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=180,
    )
    if completed.returncode != 0:
        raise RuntimeError(f"ffmpeg 抽帧失败: {completed.stderr[-1000:]}")

    frames = sorted(out_dir.glob("frame_*.jpg"))
    pts_times = [
        float(value)
        for value in re.findall(r"pts_time:([+-]?(?:\d+(?:\.\d*)?|\.\d+))", completed.stderr)
    ]
    result = []
    for i, frame in enumerate(frames):
        if i < len(pts_times):
            timestamp = pts_times[i]
        elif method == "interval":
            timestamp = min(i / fps_val, duration)
        else:
            # scene 模式无法从文件序号反推时间；缺失时明确使用保守回退值
            timestamp = 0.0 if not result else result[-1][0]
        result.append((timestamp, frame))
    return result, duration


def analyze_video_via_frames(video_path, system_prompt, user_prompt,
                             model=None, max_frames=16, method="interval",
                             base_url=None, api_key=None):
    """
    切帧 + 多模态 LLM 分析。返回 raw_text（JSON + Markdown），格式与 run_gemini 对齐。
    """
    try:
        from openai import OpenAI
    except ImportError:
        print("❌ 需要安装 openai: pip install openai", file=sys.stderr)
        sys.exit(1)

    _api_key = api_key or os.environ.get("ZENMUX_API_KEY")
    if not _api_key:
        raise RuntimeError("请设置环境变量 ZENMUX_API_KEY")
    _base_url = base_url or os.environ.get("ZENMUX_BASE_URL", DEFAULT_BASE_URL)
    _model = model or os.environ.get("VISION_MODEL", DEFAULT_VISION_MODEL)

    tmp_dir = Path(tempfile.mkdtemp(prefix="frames_"))
    try:
        print(f"正在用 ffmpeg 抽帧（method={method}, max_frames={max_frames}）...")
        frames, duration = extract_keyframes(video_path, tmp_dir, max_frames, method)
        if not frames:
            raise RuntimeError("ffmpeg 未抽取到任何帧，请检查视频文件或 ffmpeg 安装")
        print(f"共抽取 {len(frames)} 帧，视频时长约 {duration:.1f}s")

        intro = (
            f"\n\n以下是从一段时长约 {duration:.1f} 秒的视频中，按时间顺序抽取的 "
            f"{len(frames)} 张关键帧（每张标注 FFmpeg 记录的真实视频时间戳）。"
            f"请把它们视作离散证据，而不是完整连续动作。"
            f"⚠️ 未在帧中明确出现的道具、拿取、换手、开锁方式、人物路线和室内陈设不得补写；"
            f"帧间运动无法确认时必须标注 uncertain。若日期/服装突变，应判断为剪辑合集，不能串成一条连续录像。"
            f"时间轴(timeline)请对齐到这些真实时间戳。"
        )
        content = [{"type": "text", "text": user_prompt + intro}]
        for ts, fpath in frames:
            b64 = base64.b64encode(Path(fpath).read_bytes()).decode()
            content.append({"type": "text", "text": f"[关键帧 @ 约 {ts:.1f}s]"})
            content.append({
                "type": "image_url",
                "image_url": {"url": f"data:image/jpeg;base64,{b64}"},
            })

        client = OpenAI(base_url=_base_url, api_key=_api_key)
        print(f"调用多模态 LLM 分析关键帧（模型: {_model}）...")
        resp = client.chat.completions.create(
            model=_model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": content},
            ],
            max_tokens=16000,
            temperature=0.4,
        )
        return resp.choices[0].message.content
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def main():
    """
    CLI：只抽帧导出（不调 LLM），用于「由 agent 在对话内读图分析」的工作流。
    用法：python frame_analyzer.py <video> --out-dir <dir> [--max-frames N] [--method interval|scene]
    """
    import argparse

    p = argparse.ArgumentParser(
        description="抽取视频关键帧到目录（供 agent 在对话内 read_file 读图分析）"
    )
    p.add_argument("video")
    p.add_argument("--out-dir", required=True, help="关键帧输出目录")
    p.add_argument("--max-frames", type=int, default=16)
    p.add_argument("--method", default="interval", choices=["interval", "scene"])
    args = p.parse_args()

    frames, duration = extract_keyframes(
        args.video, args.out_dir, args.max_frames, args.method
    )
    print(f"✅ 视频时长约 {duration:.1f}s，已抽取 {len(frames)} 帧到 {args.out_dir}")
    for ts, f in frames:
        print(f"  约 {ts:6.1f}s  {f}")


if __name__ == "__main__":
    main()
