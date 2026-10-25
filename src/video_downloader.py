#!/usr/bin/env python3
"""视频下载模块

给定一个分享链接（抖音 / TikTok / 快手 / B站 / YouTube 等），
自动解析并下载对应视频到本地 downloads/ 目录，返回本地文件路径，
以便直接衔接 frame_analyzer.py 的抽帧流程。

依赖：yt-dlp（支持上千个平台）。若未安装：
    pip install yt-dlp
另建议安装 ffmpeg（用于音视频合并 / 转码），未安装时多数单文件视频仍可下载。

用法（命令行）：
    python video_downloader.py "<分享链接>" [--out-dir ../downloads] [--name 0705_004]

也可从粘贴的整段分享文案里自动提取链接，例如抖音的：
    "7.68 复制打开抖音，看看【xxx的作品】... https://v.douyin.com/xxxxx/ ..."
"""
from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys

# 仅允许 http/https 公网链接；用于阻断 file:// 等本地协议与明显的内网地址（SSRF 基本防护）
_URL_RE = re.compile(r"https?://[^\s，,。、）)】\]\"']+", re.IGNORECASE)

# 常见内网/保留网段（拒绝，避免 SSRF）。如确需访问内网，请人工确认后再放开。
_BLOCKED_HOST_RE = re.compile(
    r"^(localhost|127\.|0\.0\.0\.0|10\.|169\.254\.|"
    r"192\.168\.|172\.(1[6-9]|2\d|3[01])\.)",
    re.IGNORECASE,
)


def extract_url(text: str) -> str | None:
    """从一段文本（可能是整段分享文案）里提取第一个 http/https 链接。"""
    if not text:
        return None
    m = _URL_RE.search(text.strip())
    return m.group(0) if m else None


def _is_safe_url(url: str) -> bool:
    """基础安全校验：必须是 http/https，且不指向本地/内网地址。"""
    from urllib.parse import urlparse

    try:
        parsed = urlparse(url)
    except Exception:
        return False
    if parsed.scheme not in ("http", "https"):
        return False
    host = parsed.hostname or ""
    if _BLOCKED_HOST_RE.match(host):
        return False
    return True


def _ensure_yt_dlp() -> str:
    """确认 yt-dlp 可用，返回可调用的命令名/路径。"""
    exe = shutil.which("yt-dlp")
    if exe:
        return exe
    # 退而求其次：尝试以 python -m yt_dlp 方式调用
    try:
        subprocess.run(
            [sys.executable, "-m", "yt_dlp", "--version"],
            check=True,
            capture_output=True,
        )
        return f"{sys.executable} -m yt_dlp"
    except Exception as e:  # noqa: BLE001
        raise RuntimeError(
            "未检测到 yt-dlp。请先安装：pip install yt-dlp\n"
            "（用于解析并下载抖音/TikTok/B站/YouTube 等平台的视频）"
        ) from e


def download_video(
    url_or_text: str,
    out_dir: str = "downloads",
    name: str | None = None,
) -> str:
    """下载视频到 out_dir，返回本地视频文件路径。

    Args:
        url_or_text: 视频链接，或包含链接的整段分享文案（会自动提取链接）。
        out_dir: 下载目录。
        name: 可选，指定输出文件名（不含扩展名）；不指定则用平台标题。

    Returns:
        下载得到的本地视频文件绝对路径。
    """
    url = extract_url(url_or_text) or url_or_text.strip()
    if not _is_safe_url(url):
        raise ValueError(
            f"链接不合法或指向本地/内网地址，已拒绝：{url!r}\n"
            "仅支持公网 http/https 视频链接。"
        )

    os.makedirs(out_dir, exist_ok=True)
    yt_dlp = _ensure_yt_dlp()

    # 输出模板：优先用用户指定的 name，否则用视频标题（限制长度、去掉异常字符）
    if name:
        out_tmpl = os.path.join(out_dir, f"{name}.%(ext)s")
    else:
        out_tmpl = os.path.join(out_dir, "%(title).80s [%(id)s].%(ext)s")

    cmd = yt_dlp.split() if " " in yt_dlp else [yt_dlp]
    cmd += [
        "--no-playlist",              # 只下单个视频，不下整个列表
        "--merge-output-format", "mp4",
        "-f", "bv*+ba/b",            # 最佳画质+音频，退化到单一最佳流
        "-o", out_tmpl,
        "--print", "after_move:filepath",  # 下载完成后打印最终文件路径
        "--no-warnings",
        url,
    ]

    print(f"[video_downloader] 正在下载: {url}")
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(
            "视频下载失败。可能原因：链接失效 / 平台需要登录 / 需要更新 yt-dlp。\n"
            f"yt-dlp 输出：\n{result.stderr.strip()}"
        )

    # after_move:filepath 会把最终路径打印到 stdout（可能有多行，取最后一个存在的文件）
    filepath = ""
    for line in reversed(result.stdout.strip().splitlines()):
        line = line.strip()
        if line and os.path.exists(line):
            filepath = line
            break

    if not filepath:
        raise RuntimeError(
            "下载似乎完成，但未能定位到输出文件。\n"
            f"yt-dlp 输出：\n{result.stdout.strip()}"
        )

    filepath = os.path.abspath(filepath)
    print(f"[video_downloader] 下载完成 -> {filepath}")
    return filepath


def main() -> None:
    parser = argparse.ArgumentParser(description="从分享链接下载视频到本地")
    parser.add_argument("url", help="视频链接，或包含链接的整段分享文案")
    parser.add_argument(
        "--out-dir",
        default="downloads",
        help="下载目录（默认 downloads）",
    )
    parser.add_argument(
        "--name",
        default=None,
        help="可选，指定输出文件名（不含扩展名），如 0705_004",
    )
    args = parser.parse_args()

    path = download_video(args.url, out_dir=args.out_dir, name=args.name)
    # 把最终路径打印到 stdout 末行，方便脚本/agent 直接取用
    print(path)


if __name__ == "__main__":
    main()
