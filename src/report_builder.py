"""
report_builder.py

Turn a finished case directory (analysis.json + optional prompts.md + source video)
into a single-file interactive HTML report.

Division of labour:
  - Code measures: duration / fps / resolution, scene cuts, per-frame motion,
    brightness, audio loudness + onsets, dominant palette, keyframes.
  - The model's judgement comes from analysis.json (beats, hook, mechanisms ...).
  - Checks reconcile the two: every claim that can be measured is measured.

Usage:
  python report_builder.py ../output/0822_003                     # one case
  python report_builder.py ../output/0822_003 --video ../downloads/0822/3.mp4
  python report_builder.py --all ../output                        # every case + index
  python report_builder.py --index ../output                      # index page only

Only stdlib + ffmpeg/ffprobe. No API key.
"""

from __future__ import annotations

import base64
import hashlib
import html
import json
import math
import os
import random
import re
import statistics
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path

ASSET_DIR = Path(__file__).parent / "report_assets"
PROJECT_ROOT = Path(__file__).resolve().parent.parent

MEASURE_VERSION = 3
PARAMS = {
    "scene_threshold": 0.3,   # ffmpeg scene score above which a cut is detected
    "min_shot_seconds": 0.3,  # shorter fragments are merged (flashes, subtitle jumps)
    "motion_hz": 10,          # motion / brightness sampling rate
    "audio_hz": 20,           # loudness sampling rate
    "static_max_motion": 1.5, # median motion below this = picture barely moves
    "busy_min_motion": 12.0,  # median motion above this = picture moves a lot
    "onset_rise_db": 4.5,     # loudness jump that counts as an audio onset
    "sync_tolerance": 0.12,   # cut within this many seconds of an onset = on beat
}

NARRATIVE_FUNCTIONS = ["hook", "setup", "build", "twist", "payoff", "ending"]


# --------------------------------------------------------------------------
# ffmpeg layer: everything measurable is measured here
# --------------------------------------------------------------------------

def _run(cmd: list[str], timeout: int = 600) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, timeout=timeout)


def probe(video: Path) -> dict:
    """ffprobe: duration, fps, resolution, codecs, audio presence."""
    out = _run([
        "ffprobe", "-v", "error", "-print_format", "json",
        "-show_entries", "format=duration",
        "-show_entries", "stream=codec_type,codec_name,width,height,r_frame_rate",
        "-show_entries", "stream_side_data=rotation",
        str(video),
    ])
    if out.returncode != 0:
        raise RuntimeError(f"ffprobe failed: {out.stderr.decode(errors='ignore')[-400:]}")
    data = json.loads(out.stdout or b"{}")
    streams = data.get("streams", [])
    v = next((s for s in streams if s.get("codec_type") == "video"), None)
    if not v:
        raise RuntimeError(f"No video stream in {video}")
    num, _, den = str(v.get("r_frame_rate", "0/1")).partition("/")
    fps = float(num) / float(den or 1) if float(den or 1) else 0.0
    w, h = int(v.get("width") or 0), int(v.get("height") or 0)
    rotation = 0
    for sd in v.get("side_data_list", []) or []:
        if "rotation" in sd:
            rotation = int(sd["rotation"])
    if abs(rotation) in (90, 270):
        w, h = h, w
    a = next((s for s in streams if s.get("codec_type") == "audio"), None)
    return {
        "duration": round(float(data.get("format", {}).get("duration") or 0), 2),
        "fps": round(fps, 2),
        "width": w,
        "height": h,
        "aspect": aspect_of(w, h),
        "video_codec": v.get("codec_name", ""),
        "audio_codec": (a or {}).get("codec_name", ""),
        "has_audio": a is not None,
    }


def aspect_of(w: int, h: int) -> str:
    """Reduce a resolution to a readable aspect ratio, snapping to common ones."""
    if not w or not h:
        return ""
    ratio = w / h
    common = {"9:16": 9 / 16, "16:9": 16 / 9, "1:1": 1.0, "4:3": 4 / 3, "3:4": 3 / 4,
              "4:5": 4 / 5, "21:9": 21 / 9, "2:3": 2 / 3, "3:2": 3 / 2,
              "16:10": 16 / 10, "10:16": 10 / 16}
    name, val = min(common.items(), key=lambda kv: abs(kv[1] - ratio))
    if abs(val - ratio) / val < 0.02:
        return name
    g = math.gcd(w, h)
    return f"{w // g}:{h // g}"


def ratio_of(text: str) -> float | None:
    """First `W:H` / `WxH` pair in free text, as a float. '581:360（1162x720）' -> 1.614."""
    m = re.search(r"(\d+(?:\.\d+)?)\s*[:：xX×]\s*(\d+(?:\.\d+)?)", text or "")
    if not m or float(m.group(2)) == 0:
        return None
    return float(m.group(1)) / float(m.group(2))


def _parse_metadata(path: Path, key: str) -> list[tuple[float, float]]:
    """Parse ffmpeg `metadata=print` output into (pts_time, value) pairs."""
    if not path.exists():
        return []
    pairs, t = [], None
    for line in path.read_text(errors="ignore").splitlines():
        m = re.search(r"pts_time:([0-9.]+)", line)
        if m:
            t = float(m.group(1))
            continue
        if key in line and t is not None:
            try:
                val = float(line.split("=", 1)[1])
            except ValueError:
                continue
            pairs.append((t, val))
    return pairs


def measure_video(video: Path, threshold: float) -> dict:
    """One decode pass: scene cuts + motion curve + brightness curve."""
    hz = PARAMS["motion_hz"]
    with tempfile.TemporaryDirectory(prefix="vca_measure_") as tmp:
        tmp = Path(tmp)
        cuts_f, bright_f, motion_f = tmp / "cuts.txt", tmp / "bright.txt", tmp / "motion.txt"
        graph = (
            "[0:v]scale=320:-2,split=2[s][m];"
            # eq(n,0) keeps frame 0 so a one-take video still feeds the null muxer
            f"[s]select='eq(n\\,0)+gt(scene\\,{threshold})',metadata=print:file={cuts_f}[o1];"
            f"[m]fps={hz},scale=64:36,split=2[b][d];"
            f"[b]signalstats,metadata=print:key=lavfi.signalstats.YAVG:file={bright_f}[o2];"
            f"[d]tblend=all_mode=difference,signalstats,"
            f"metadata=print:key=lavfi.signalstats.YAVG:file={motion_f}[o3]"
        )
        out = _run([
            "ffmpeg", "-v", "error", "-nostdin", "-i", str(video), "-an",
            "-filter_complex", graph,
            "-map", "[o1]", "-f", "null", "-",
            "-map", "[o2]", "-f", "null", "-",
            "-map", "[o3]", "-f", "null", "-",
        ])
        if out.returncode != 0:
            raise RuntimeError(f"ffmpeg measure failed: {out.stderr.decode(errors='ignore')[-400:]}")
        cuts = [(round(t, 2), round(v, 3)) for t, v in _parse_metadata(cuts_f, "scene_score")
                if t > 0.05 and v > threshold]
        motion = [round(v, 2) for _, v in _parse_metadata(motion_f, "YAVG")]
        bright = [round(v, 1) for _, v in _parse_metadata(bright_f, "YAVG")]
    # tblend drops the first frame: pad so index i maps to time i / hz
    if motion:
        motion = [motion[0]] + motion
    return {"cuts": cuts, "motion": {"hz": hz, "values": motion},
            "brightness": {"hz": hz, "values": bright}}


def measure_audio(video: Path) -> dict:
    """Loudness curve (RMS dBFS) at audio_hz samples per second."""
    hz = PARAMS["audio_hz"]
    rate = 8000
    out = _run([
        "ffmpeg", "-v", "error", "-nostdin", "-i", str(video), "-vn",
        "-af", f"aresample={rate},asetnsamples=n={rate // hz}:p=0,astats=metadata=1:reset=1,"
               "ametadata=print:key=lavfi.astats.Overall.RMS_level:file=-",
        "-f", "null", "-",
    ])
    values = []
    for line in out.stdout.decode(errors="ignore").splitlines():
        if "RMS_level=" in line:
            raw = line.split("=", 1)[1].strip()
            try:
                v = float(raw)
            except ValueError:
                v = -90.0
            values.append(round(max(-90.0, v if math.isfinite(v) else -90.0), 1))
    return {"hz": hz, "values": values}


def detect_onsets(audio: dict, rise_db: float) -> list[float]:
    """
    Heuristic onset detection on the loudness curve: a sample that jumps at least
    `rise_db` above the minimum of the previous ~150 ms and is a local maximum.
    It is an estimate, not a beat tracker; the report labels it as such.
    """
    vals, hz = audio.get("values", []), audio.get("hz", 20)
    if len(vals) < 4:
        return []
    floor = statistics.median(vals) - 18
    look = max(2, int(0.15 * hz))
    min_gap = 0.15
    onsets: list[float] = []
    for i in range(1, len(vals) - 1):
        if vals[i] < floor:
            continue
        prev_min = min(vals[max(0, i - look):i])
        if vals[i] - prev_min < rise_db:
            continue
        if vals[i] < vals[i + 1]:
            continue
        t = round(i / hz, 2)
        if onsets and t - onsets[-1] < min_gap:
            continue
        onsets.append(t)
    return onsets


def build_shots(cuts: list[float], duration: float, min_shot: float) -> list[dict]:
    """Shot list from measured cuts; fragments shorter than min_shot are merged."""
    bounds = [0.0]
    for t in sorted(set(c for c in cuts if 0 < c < duration)):
        if t - bounds[-1] >= min_shot:
            bounds.append(t)
    if len(bounds) > 1 and duration - bounds[-1] < min_shot:
        bounds.pop()
    bounds.append(duration)
    return [
        {"id": f"S{i + 1:02d}", "start": round(bounds[i], 2), "end": round(bounds[i + 1], 2),
         "seconds": round(bounds[i + 1] - bounds[i], 2)}
        for i in range(len(bounds) - 1)
    ]


def median_in(track: dict, start: float, end: float) -> float | None:
    """
    Median of a curve inside [start, end], trimming both edges so the spike at a
    cut does not make every segment look like it moves.
    """
    vals, hz = (track or {}).get("values") or [], (track or {}).get("hz") or 0
    span = end - start
    if not vals or not hz or span <= 0:
        return None
    edge = min(0.4, max(0.1, span * 0.15))
    lo, hi = math.ceil((start + edge) * hz), math.floor((end - edge) * hz)
    window = [v for v in vals[max(0, lo):max(0, hi) + 1] if isinstance(v, (int, float))]
    if not window:
        lo, hi = int(start * hz), int(math.ceil(end * hz))
        window = [v for v in vals[max(0, lo):max(0, hi) + 1] if isinstance(v, (int, float))]
    return round(statistics.median(window), 2) if window else None


def sync_rate(cut_times: list[float], onsets: list[float], tol: float) -> dict:
    """Share of measured cuts that land within `tol` seconds of an audio onset."""
    if not cut_times or not onsets:
        return {"rate": None, "hits": [], "total": len(cut_times)}
    hits = [c for c in cut_times if any(abs(c - o) <= tol for o in onsets)]
    return {"rate": round(len(hits) / len(cut_times), 3), "hits": hits, "total": len(cut_times)}


def extract_palette(video: Path, duration: float, k: int = 6) -> list[dict]:
    """Dominant colours via tiny rgb24 samples + k-means (stdlib only)."""
    fps = max(0.5, min(4.0, 24 / max(duration, 1)))
    out = _run([
        "ffmpeg", "-v", "error", "-nostdin", "-i", str(video), "-an",
        "-vf", f"fps={fps:.3f},scale=24:24:flags=area,format=rgb24",
        "-f", "rawvideo", "-",
    ])
    raw = out.stdout
    pixels = [tuple(raw[i:i + 3]) for i in range(0, len(raw) - 2, 3)]
    if len(pixels) < k:
        return []
    rnd = random.Random(7)
    if len(pixels) > 6000:
        pixels = rnd.sample(pixels, 6000)
    centers = rnd.sample(pixels, k)
    for _ in range(12):
        groups: list[list[tuple]] = [[] for _ in range(k)]
        for p in pixels:
            j = min(range(k), key=lambda c: (p[0] - centers[c][0]) ** 2
                    + (p[1] - centers[c][1]) ** 2 + (p[2] - centers[c][2]) ** 2)
            groups[j].append(p)
        centers = [
            tuple(sum(ch) / len(g) for ch in zip(*g)) if g else centers[i]
            for i, g in enumerate(groups)
        ]
    total = len(pixels)
    result = [
        {"hex": "#%02x%02x%02x" % tuple(int(round(c)) for c in centers[i]),
         "pct": round(len(g) / total, 3)}
        for i, g in enumerate(groups) if g
    ]
    return sorted(result, key=lambda x: -x["pct"])


def grab_frame(video: Path, t: float, dest: Path, width: int = 360) -> bool:
    """Extract one JPEG at time t (accurate seek)."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    out = _run([
        "ffmpeg", "-v", "error", "-nostdin", "-y", "-ss", f"{max(0.0, t):.3f}", "-i", str(video),
        "-frames:v", "1", "-vf", f"scale={width}:-2", "-q:v", "4", str(dest),
    ], timeout=60)
    return out.returncode == 0 and dest.exists() and dest.stat().st_size > 0


def needs_proxy(info: dict) -> bool:
    """HEVC and >1080p sources play poorly (or not at all) in many Chromium builds."""
    return info.get("video_codec") not in ("h264", "vp9", "av1") or max(info["width"], info["height"]) > 1920


def make_proxy(video: Path, dest: Path, info: dict) -> Path | None:
    """720p H.264 + AAC proxy with faststart, reused while the source is unchanged."""
    if dest.exists() and dest.stat().st_mtime >= video.stat().st_mtime and dest.stat().st_size > 0:
        return dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    scale = "scale=-2:1280" if info["height"] >= info["width"] else "scale=1280:-2"
    out = _run([
        "ffmpeg", "-v", "error", "-nostdin", "-y", "-i", str(video),
        "-vf", f"{scale}:flags=bicubic", "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
        "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart", str(dest),
    ], timeout=900)
    return dest if out.returncode == 0 and dest.exists() else None


def grab_filmstrip(video: Path, duration: float, dest_dir: Path, count: int) -> list[dict]:
    """Evenly spaced small thumbnails for hover-scrub preview."""
    dest_dir.mkdir(parents=True, exist_ok=True)
    for old in dest_dir.glob("strip_*.jpg"):
        old.unlink()
    fps = count / max(duration, 0.1)
    out = _run([
        "ffmpeg", "-v", "error", "-nostdin", "-y", "-i", str(video), "-an",
        "-vf", f"fps={fps:.4f},scale=160:-2", "-q:v", "6", "-frames:v", str(count),
        str(dest_dir / "strip_%03d.jpg"),
    ])
    if out.returncode != 0:
        return []
    files = sorted(dest_dir.glob("strip_*.jpg"))
    return [{"t": round((i + 0.5) / fps, 2), "path": f} for i, f in enumerate(files)]


# --------------------------------------------------------------------------
# Measurement cache: measure.json is machine evidence, do not hand-edit
# --------------------------------------------------------------------------

def _fingerprint(video: Path, threshold: float) -> str:
    st = video.stat()
    key = f"{MEASURE_VERSION}|{video.resolve()}|{st.st_size}|{int(st.st_mtime)}|{threshold}"
    return hashlib.sha1(key.encode()).hexdigest()[:16]


def load_or_measure(video: Path, case_dir: Path, threshold: float, force: bool = False) -> dict:
    cache = case_dir / "measure.json"
    fp = _fingerprint(video, threshold)
    if cache.exists() and not force:
        try:
            data = json.loads(cache.read_text(encoding="utf-8"))
            if data.get("fingerprint") == fp:
                return data
        except (json.JSONDecodeError, OSError):
            pass
    info = probe(video)
    vis = measure_video(video, threshold)
    audio = measure_audio(video) if info["has_audio"] else {"hz": PARAMS["audio_hz"], "values": []}
    onsets = detect_onsets(audio, PARAMS["onset_rise_db"])
    cut_times = [t for t, _ in vis["cuts"]]
    shots = build_shots(cut_times, info["duration"], PARAMS["min_shot_seconds"])
    for s in shots:
        s["motion"] = median_in(vis["motion"], s["start"], s["end"])
    kept_cuts = [s["start"] for s in shots[1:]]
    data = {
        "fingerprint": fp,
        "version": MEASURE_VERSION,
        "source": str(video),
        "params": {**PARAMS, "scene_threshold": threshold},
        "probe": info,
        "raw_cuts": vis["cuts"],
        "shots": shots,
        "motion": vis["motion"],
        "brightness": vis["brightness"],
        "audio": audio,
        "onsets": onsets,
        "sync": sync_rate(kept_cuts, onsets, PARAMS["sync_tolerance"]),
        "palette": extract_palette(video, info["duration"]),
    }
    cache.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return data


# --------------------------------------------------------------------------
# Inputs from the analysis side
# --------------------------------------------------------------------------

def guess_video(case_dir: Path, analysis: dict) -> Path | None:
    """
    Find the source video: analysis.meta.source, then the downloads/<MMDD>/<NNN>.mp4
    convention used by this repo (case dir `0822_003_pub` -> downloads/0822/3.mp4 or 003.mp4).
    """
    src = (analysis.get("meta") or {}).get("source")
    if src:
        for cand in (Path(src), case_dir / src, PROJECT_ROOT / src):
            if cand.is_file():
                return cand
    m = re.match(r"^(\d{4})_(\d+)", case_dir.name)
    if m:
        day, num = m.group(1), m.group(2)
        folder = PROJECT_ROOT / "downloads" / day
        for name in (num, str(int(num)), f"{int(num):03d}"):
            for ext in (".mp4", ".mov", ".webm", ".mkv"):
                cand = folder / f"{name}{ext}"
                if cand.is_file():
                    return cand
    return None


def parse_prompts_md(text: str) -> dict:
    """
    Split prompts.md into intro + versions (## headings) + blocks (### headings).
    Works for the A/B/C contract and degrades gracefully for older formats.
    """
    intro_lines: list[str] = []
    versions: list[dict] = []
    title = ""
    cur_v: dict | None = None
    cur_b: dict | None = None
    for line in text.splitlines():
        if line.startswith("# ") and not title:
            title = line[2:].strip()
            continue
        if line.startswith("## "):
            cur_v = {"title": line[3:].strip(), "blocks": []}
            cur_b = None
            versions.append(cur_v)
            continue
        if line.startswith("### ") and cur_v is not None:
            cur_b = {"title": line[4:].strip(), "body": []}
            cur_v["blocks"].append(cur_b)
            continue
        if cur_v is None:
            intro_lines.append(line)
        else:
            if cur_b is None:
                cur_b = {"title": "", "body": []}
                cur_v["blocks"].append(cur_b)
            cur_b["body"].append(line)

    def clean(lines: list[str]) -> str:
        body = "\n".join(l for l in lines if not l.strip().startswith("```"))
        return body.strip()

    for v in versions:
        v["blocks"] = [{"title": b["title"], "body": clean(b["body"])} for b in v["blocks"]]
        v["blocks"] = [b for b in v["blocks"] if b["body"]]
    intro = "\n".join(l[1:].strip() if l.startswith(">") else l for l in intro_lines).strip()
    return {"title": title, "intro": intro, "versions": [v for v in versions if v["blocks"]]}


VERSION_RE = re.compile(r"版本\s*[A-Z]\b|版本\s*[A-Z][\s·:：]|变体\s*[①-⑩\d]")
PARTIAL_RE = re.compile(r"只替换|替换为|其余[^。\n]{0,30}不变|与原版[^。\n]{0,10}一致|同上")
IMAGE_HEAD_RE = re.compile(r"参考图|人物|角色|首帧|图片素材|形象")
VIDEO_HEAD_RE = re.compile(r"视频|Seedance|I2V|即梦")


def _fenced_blocks(text: str) -> tuple[list[dict], str, dict]:
    """
    Legacy prompt files put every paste-ready prompt inside a ``` fence. Collect each
    fence with its heading context (h2 / h3 / last bold label) and the section prose.
    """
    blocks: list[dict] = []
    h1 = h2 = h3 = label = ""
    section_prose: dict[tuple, list[str]] = {}
    in_fence, buf = False, []
    for line in text.splitlines():
        if line.strip().startswith("```"):
            if in_fence:
                blocks.append({"h2": h2, "h3": h3, "label": label, "body": "\n".join(buf).strip()})
                buf, label = [], ""
            in_fence = not in_fence
            continue
        if in_fence:
            buf.append(line)
            continue
        if line.startswith("# "):
            h1 = line[2:].strip()
        elif line.startswith("## "):
            h2, h3, label = line[3:].strip(), "", ""
        elif line.startswith("### "):
            h3, label = line[4:].strip(), ""
            section_prose.setdefault((h2, h3), [])
        else:
            m = re.match(r"^\s*\*\*(.+?)\*\*\s*[:：]?\s*$", line)
            if m:
                label = m.group(1).strip("【】 ")
            section_prose.setdefault((h2, h3), []).append(line)
    for b in blocks:
        prose = "\n".join(section_prose.get((b["h2"], b["h3"]), []))
        b["partial"] = bool(PARTIAL_RE.search(b["body"][:200])
                            or (PARTIAL_RE.search(prose) and len(b["body"]) < 200))
    return [b for b in blocks if b["body"]], h1, section_prose


def _clean_title(text: str) -> str:
    t = re.sub(r"`[^`]*`", "", text)
    t = re.sub(r"^第\s*\d+\s*步\s*[·▍|]?\s*", "", t)
    t = re.sub(r"\s+(主角|配角|背景角色)\b.*$", "", t)  # "长发女生  `char_A`  主角  出现于 Shot 1"
    t = re.sub(r"\s+注意力[:：]\s*\d/\d", "", t)
    t = t.replace("【", "").replace("】", " · ").replace("🖼️", "").replace("🎬", "")
    return re.sub(r"[\s·:：]+$", "", re.sub(r"\s{2,}", " ", t)).strip(" ·")


def _block_title(b: dict, drop: str = "") -> str:
    # inside a version tab keyed by h3, the h2 is only the "第 2 步 · ..." container
    heads = (b["h3"],) if drop and drop == b["h3"] else (b["h2"], b["h3"])
    parts = [h for h in heads if h and h != drop]
    head = _clean_title(parts[-1]) if parts else ""
    if b["h3"] and b["h2"] != drop and "角色参考图" in b["h2"] and head:
        head = f"{head} · 人物参考图"
    label = _clean_title(b["label"])
    if label and label not in head:
        head = f"{head} · {label}" if head else label
    return head or "Prompt"


def parse_legacy_prompts(files: list[tuple[str, str]]) -> dict:
    """
    Build copy-ready tabs from pre-A/B/C files (shot_prompts.md, variant_prompts.md, ...).
    Every tab carries the shared character/first-frame prompts of its file so a tab
    is a complete set; fragments that only patch the original are flagged `partial`.
    """
    versions: list[dict] = []
    directions: list[dict] = []
    for name, text in files:
        blocks, h1, prose = _fenced_blocks(text)
        has_full_variants = False
        keyed: dict[str, list[dict]] = {}
        shared: list[dict] = []
        for b in blocks:
            key = next((h for h in (b["h3"], b["h2"]) if VERSION_RE.search(h)), "")
            if not key and "变体方向" in b["h2"] and b["h3"]:
                key = b["h3"]
            if key:
                keyed.setdefault(key, []).append(b)
            else:
                shared.append(b)
        shared_images = [b for b in shared if IMAGE_HEAD_RE.search(b["h2"] + b["h3"])]
        if keyed:
            base = [b for b in shared if VIDEO_HEAD_RE.search(b["h2"] + b["h3"]) or b in shared_images]
            if name == "shot_prompts.md" and base:
                versions.append({"title": "原版 · 完整 Prompt", "source": name,
                                 "blocks": [_as_block(b) for b in base]})
            for key, own in keyed.items():
                partial = all(b["partial"] for b in own)
                has_image = any(IMAGE_HEAD_RE.search(b["label"] + b["h3"]) for b in own)
                lead = [] if has_image or partial else [_as_block(b, prefix="公共") for b in shared_images]
                versions.append({"title": _clean_title(key), "source": name, "partial": partial,
                                 "blocks": lead + [_as_block(b, drop=key) for b in own]})
                has_full_variants = has_full_variants or not partial
        elif blocks:
            title = "原版 · 完整 Prompt" if name == "shot_prompts.md" else (h1 or name)
            versions.append({"title": title, "source": name, "blocks": [_as_block(b) for b in blocks]})
        # one-line "变体方向" ideas: headings without any fenced prompt
        for (h2, h3), lines in prose.items():
            if "变体方向" in h2 and h3 and not any(b["h3"] == h3 for b in blocks):
                directions.append({"title": h3, "text": "\n".join(l for l in lines if l.strip()).strip(),
                                   "source": name})
        if has_full_variants:
            directions = [d for d in directions if d["source"] != "shot_prompts.md"]
    return {"title": "", "intro": "", "legacy": True, "versions": versions, "directions": directions,
            "source": " + ".join(n for n, _ in files)}


def _as_block(b: dict, drop: str = "", prefix: str = "") -> dict:
    title = _block_title(b, drop)
    if title == "Prompt" and drop:
        title = "视频 Prompt" if not IMAGE_HEAD_RE.search(b["label"]) else "人物参考图 Prompt"
    return {"title": f"{prefix} · {title}" if prefix else title, "body": b["body"], "partial": b["partial"]}


def load_prompts(case_dir: Path) -> dict | None:
    """prompts.md is the A/B/C deliverable; older cases fall back to the legacy files."""
    p = case_dir / "prompts.md"
    if p.exists():
        prompts = parse_prompts_md(p.read_text(encoding="utf-8"))
        prompts["source"] = "prompts.md"
        return prompts
    names = ["shot_prompts.md", "variant_prompts.md"]
    names += sorted(f.name for f in case_dir.glob("*prompts.md") if f.name not in names)
    files = [(n, (case_dir / n).read_text(encoding="utf-8")) for n in names if (case_dir / n).exists()]
    return parse_legacy_prompts(files) if files else None


def _fmt_time(ts: float) -> str:
    return datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M")


def stamp_prompts(case_dir: Path, prompts: dict | None) -> None:
    """
    Give every prompt block its own "last updated" time. Blocks are fingerprinted by
    content hash in prompt_history.json, so editing only one reference-image or video
    prompt bumps just that block; unseen blocks start at their source file's mtime.
    """
    if not prompts or not prompts.get("versions"):
        return
    hist_path = case_dir / "prompt_history.json"
    try:
        hist = json.loads(hist_path.read_text(encoding="utf-8")) if hist_path.exists() else {}
    except json.JSONDecodeError:
        hist = {}
    now = datetime.now().timestamp()
    new_hist: dict[str, dict] = {}
    for v in prompts["versions"]:
        src = case_dir / (v.get("source") or prompts.get("source") or "prompts.md")
        base_ts = src.stat().st_mtime if src.exists() else now
        seen: dict[str, int] = {}
        for b in v["blocks"]:
            key = f"{v['title']}|{b['title']}"
            seen[key] = seen.get(key, 0) + 1
            if seen[key] > 1:
                key = f"{key}#{seen[key]}"
            digest = hashlib.sha1(b["body"].encode("utf-8")).hexdigest()
            old = hist.get(key)
            if old and old.get("hash") == digest:
                ts = float(old.get("ts") or base_ts)
            else:
                ts = now if old else base_ts
            new_hist[key] = {"hash": digest, "ts": ts}
            b["updated_at"] = _fmt_time(ts)
            b["updated_ts"] = int(ts)
        if v["blocks"]:
            latest = max(b["updated_ts"] for b in v["blocks"])
            v["updated_at"] = _fmt_time(latest)
            v["updated_ts"] = latest
    if new_hist != hist:
        hist_path.write_text(json.dumps(new_hist, ensure_ascii=False, indent=1), encoding="utf-8")


def case_updated_ts(case_dir: Path) -> float:
    """Latest change among the case's editable deliverables."""
    files = [case_dir / "analysis.json", *case_dir.glob("*prompts.md")]
    ts = [f.stat().st_mtime for f in files if f.exists()]
    hp = case_dir / "prompt_history.json"
    if hp.exists():
        try:
            ts += [float(e.get("ts") or 0) for e in json.loads(hp.read_text(encoding="utf-8")).values()]
        except (json.JSONDecodeError, AttributeError):
            pass
    return max(ts) if ts else 0.0


TIMESTAMP_RE = re.compile(r"\[?\d+(?:\.\d+)?\s*[-–~至到]\s*\d+(?:\.\d+)?\s*(?:秒|s|S)\]?")


def find_prompt_timestamps(prompts: dict) -> list[str]:
    hits = []
    for v in prompts.get("versions", []):
        for b in v["blocks"]:
            for m in TIMESTAMP_RE.finditer(b["body"]):
                hits.append(f"{v['title']} / {b['title']}: {m.group(0)}")
    return hits


# --------------------------------------------------------------------------
# Reconciliation: claims vs measurements
# --------------------------------------------------------------------------

_NEGATION = re.compile(r"(不|无|没有|禁止|非|避免|拒绝|严禁)[^，。；,;、]{0,8}")
_MOVING = re.compile(r"推|拉近|拉远|摇|横移|平移|移动|跟拍|跟随|环绕|升降|甩|旋转|运镜|晃动|手持|追")
_STATIC = re.compile(r"固定|定机位|静止|三脚架|支架|监控|锁定机位")


def camera_claim(text: str) -> str:
    """Classify a camera description as 'moving', 'static', 'mixed' or ''."""
    t = _NEGATION.sub("", text or "")
    mv, st = bool(_MOVING.search(t)), bool(_STATIC.search(t))
    if mv and st:
        return "mixed"
    return "moving" if mv else "static" if st else ""


def _status(ok: bool, warn: bool = False) -> str:
    return "pass" if ok else ("warn" if warn else "fail")


def run_checks(analysis: dict, measure: dict | None, segments: list[dict], prompts: dict | None) -> list[dict]:
    checks: list[dict] = []
    meta = analysis.get("meta") or {}
    timeline = analysis.get("timeline") or []

    def add(cid, name, status, detail, refs=None):
        checks.append({"id": cid, "name": name, "status": status, "detail": detail, "refs": refs or []})

    # 1. timeline continuity (pure analysis-side check)
    problems, refs = [], []
    prev_end = 0.0
    for seg in segments:
        if seg["start"] < prev_end - 0.05:
            problems.append(f"{seg['id']} overlaps previous beat")
            refs.append(seg["id"])
        elif seg["start"] > prev_end + 0.3:
            problems.append(f"gap {prev_end:.2f}s → {seg['start']:.2f}s before {seg['id']}")
            refs.append(seg["id"])
        if seg["end"] <= seg["start"]:
            problems.append(f"{seg['id']} has non-positive length")
            refs.append(seg["id"])
        prev_end = max(prev_end, seg["end"])
    if not segments:
        add("timeline", "时间轴连续", "fail", "analysis.json 没有 timeline")
    else:
        add("timeline", "时间轴连续", "pass" if not problems else "warn",
            "节拍首尾相接、无重叠" if not problems else "；".join(problems[:4]), refs)

    # 2. required fields
    required = [("summary", "one_sentence"), ("viral_mechanics", "hook_type"),
                ("transferable_pattern", "abstract_pattern"), ("seedance_translation", "recommended_mode")]
    missing = [f"{a}.{b}" for a, b in required if not str((analysis.get(a) or {}).get(b) or "").strip()]
    add("fields", "关键字段完整", "pass" if not missing else "warn",
        "核心结论字段齐全" if not missing else "缺少：" + "、".join(missing))

    if not measure:
        for cid, name in [("duration", "片长对账"), ("aspect", "画幅对账"), ("shots", "镜头数对账"),
                          ("oneshot", "一镜到底声明"), ("camera", "运镜实测对账")]:
            add(cid, name, "skip", "未找到原视频，无法实测（可用 --video 指定）")
    else:
        info = measure["probe"]
        # 3. duration
        claimed = float(meta.get("duration_seconds") or 0)
        diff = abs(claimed - info["duration"])
        add("duration", "片长对账", "pass" if claimed and diff <= 0.5 else ("warn" if claimed else "skip"),
            f"分析写 {claimed:.2f}s，实测 {info['duration']:.2f}s" if claimed else "analysis 未写片长")
        # 4. aspect
        claimed_ar = str(meta.get("aspect_ratio") or "").strip()
        claimed_r = ratio_of(claimed_ar)
        real_r = info["width"] / info["height"] if info["height"] else None
        ar_ok = bool(claimed_r and real_r and abs(claimed_r - real_r) / real_r < 0.03)
        add("aspect", "画幅对账",
            "pass" if ar_ok else ("warn" if claimed_ar else "skip"),
            f"分析写 {claimed_ar or '—'}，实测 {info['aspect']}（{info['width']}×{info['height']}）")
        # 5. shot count
        measured_n = len(measure["shots"])
        est = meta.get("estimated_shot_count")
        if isinstance(est, (int, float)) and est > 0:
            ok = abs(est - measured_n) <= max(1, round(measured_n * 0.3))
            if ok:
                why = ""
            elif measured_n < est:
                why = "（检测偏少：同场景跳切、叠化、暗场容易漏检，可用 --threshold 0.15 重跑；也可能是模型把动作变化当成了切镜）"
            else:
                why = "（检测偏多：模型可能把快剪合并成一个节拍，也可能是闪光、快速甩动被误判为切点）"
            add("shots", "镜头数对账", "pass" if ok else "warn",
                f"分析估计 {int(est)} 镜，场景检测 {measured_n} 镜{why}")
        else:
            add("shots", "镜头数对账", "skip", "analysis 未写 estimated_shot_count")
        # 6. one-take claim vs detected cuts
        cam = analysis.get("camera_language") or {}
        claim_text = " ".join(str(cam.get(k) or "") for k in ("dominant_movement", "continuity_strategy",
                                                              "movement_continuity"))
        claims_oneshot = bool(re.search(r"一镜到底|单镜头|无切镜|不切镜|长镜头", claim_text)) or est == 1
        if claims_oneshot:
            add("oneshot", "一镜到底声明", "pass" if measured_n == 1 else "warn",
                "实测无硬切，与声明一致" if measured_n == 1
                else f"声明一镜到底，但检测到 {measured_n - 1} 个疑似切点："
                     + "、".join(f"{s['start']:.2f}s" for s in measure["shots"][1:6]))
        else:
            add("oneshot", "一镜到底声明", "skip", "未声明一镜到底")
        # 7. camera claim vs measured motion, per beat
        bad, hints = [], []
        for seg in segments:
            m, claim = seg.get("motion"), seg.get("camera_claim")
            if m is None or seg["seconds"] < 0.8:
                continue
            if claim == "moving" and m < PARAMS["static_max_motion"]:
                bad.append(seg["id"])
            elif claim == "static" and m > PARAMS["busy_min_motion"]:
                hints.append(seg["id"])
        if bad:
            status, detail = "warn", f"声称运镜但画面几乎不动：{'、'.join(bad)}"
        else:
            status, detail = "pass", "运镜描述与实测运动量不矛盾"
        if hints:
            detail += f"；声称固定但实测运动偏高（可能是主体在动）：{'、'.join(hints)}"
        add("camera", "运镜实测对账", status, detail, bad + hints)

        # 8. peak moments vs measured energy
        peaks = (analysis.get("rhythm_structure") or {}).get("peak_moments") or []
        if peaks and measure["motion"]["values"]:
            mv = measure["motion"]["values"]
            hz = measure["motion"]["hz"]
            p75 = sorted(mv)[int(len(mv) * 0.75)] if mv else 0
            onsets = measure.get("onsets", [])
            cuts = [s["start"] for s in measure["shots"][1:]]
            unsupported = []
            for p in peaks:
                t = float(p.get("time") or 0)
                window = mv[max(0, int((t - 0.5) * hz)):int((t + 0.5) * hz) + 1]
                near = (window and max(window) >= p75) or any(abs(t - o) <= 0.5 for o in onsets) \
                    or any(abs(t - c) <= 0.5 for c in cuts)
                if not near:
                    unsupported.append(f"{t:.1f}s")
            add("peaks", "峰值有实测支撑", "pass" if not unsupported else "warn",
                "每个峰值附近都有运动/切点/起音" if not unsupported
                else f"这些峰值附近没有明显的画面或声音变化：{'、'.join(unsupported)}")

    # 9. prompt contract (A/B/C + no timestamps) only binds the current prompts.md deliverable
    if prompts and prompts.get("legacy"):
        add("prompt_ts", "Prompt 交付物", "skip",
            f"旧版格式（{prompts.get('source')}），早于 A/B/C 与禁止时间戳契约，不做契约检查")
    elif prompts and prompts.get("versions"):
        hits = find_prompt_timestamps(prompts)
        add("prompt_ts", "Prompt 无时间戳", "pass" if not hits else "warn",
            "最终 prompt 未写时间段" if not hits else "发现时间段写法：" + "；".join(hits[:3]))
        n = len(prompts["versions"])
        has_video = sum(1 for v in prompts["versions"] if any("视频" in b["title"] for b in v["blocks"]))
        add("prompt_ver", "A/B/C 版本完整", "pass" if n >= 3 and has_video >= 3 else "warn",
            f"{n} 个版本，其中 {has_video} 个含视频 Prompt")
    else:
        add("prompt_ts", "Prompt 交付物", "skip", "未找到 prompts.md")
    return checks


# --------------------------------------------------------------------------
# Assemble the document consumed by report.js
# --------------------------------------------------------------------------

def data_url(path: Path) -> str:
    return "data:image/jpeg;base64," + base64.b64encode(path.read_bytes()).decode()


def build_segments(analysis: dict, measure: dict | None) -> list[dict]:
    segs = []
    for i, t in enumerate(analysis.get("timeline") or []):
        start, end = float(t.get("start") or 0), float(t.get("end") or 0)
        seg = {k: v for k, v in t.items()}
        seg.update({
            "id": f"B{i + 1:02d}",
            "start": round(start, 2),
            "end": round(end, 2),
            "seconds": round(end - start, 2),
            "camera_claim": camera_claim(f"{t.get('camera_action', '')} {t.get('camera_details', '')}"),
        })
        if measure:
            seg["motion"] = median_in(measure["motion"], start, end)
            seg["loudness"] = median_in(measure["audio"], start, end)
            seg["cuts_inside"] = sum(1 for s in measure["shots"][1:] if start < s["start"] < end)
        segs.append(seg)
    return segs


def compute_stats(analysis: dict, measure: dict | None, segments: list[dict]) -> dict:
    meta = analysis.get("meta") or {}
    duration = (measure or {}).get("probe", {}).get("duration") or float(meta.get("duration_seconds") or 0)
    stats = {"duration": round(duration, 2), "beats": len(segments)}
    if measure:
        shots = measure["shots"]
        secs = [s["seconds"] for s in shots]
        mv = [v for v in measure["motion"]["values"] if isinstance(v, (int, float))]
        stats.update({
            "shots": len(shots),
            "avg_shot": round(sum(secs) / len(secs), 2) if secs else None,
            "median_shot": round(statistics.median(secs), 2) if secs else None,
            "min_shot": min(secs) if secs else None,
            "max_shot": max(secs) if secs else None,
            "cuts_per_min": round((len(shots) - 1) / duration * 60, 1) if duration else None,
            "motion_avg": round(sum(mv) / len(mv), 2) if mv else None,
            "sync_rate": measure.get("sync", {}).get("rate"),
            "onsets": len(measure.get("onsets", [])),
        })
    else:
        stats["shots"] = meta.get("estimated_shot_count")
    return stats


def collect_frames(case_dir: Path, video: Path | None, measure: dict | None,
                   segments: list[dict], embed: bool, report_dir: Path) -> tuple[dict, list[dict]]:
    """Keyframes per beat (a = 15%, b = 85%) and a hover filmstrip."""
    assets = case_dir / "report_assets"
    frames: dict[str, dict] = {}
    strip: list[dict] = []

    def ref(path: Path) -> str:
        return data_url(path) if embed else os.path.relpath(path, report_dir)

    if video and measure:
        for seg in segments:
            span = max(seg["seconds"], 0.01)
            pair = {}
            for tag, frac in (("a", 0.15), ("b", 0.85)):
                t = min(seg["start"] + span * frac, measure["probe"]["duration"] - 0.05)
                dest = assets / f"{seg['id']}{tag}.jpg"
                if grab_frame(video, t, dest):
                    pair[tag] = ref(dest)
            frames[seg["id"]] = pair
        count = int(min(80, max(12, measure["probe"]["duration"] * 2)))
        strip = [{"t": s["t"], "src": ref(s["path"])}
                 for s in grab_filmstrip(video, measure["probe"]["duration"], assets / "strip", count)]
    else:
        # No video: fall back to frames/ extracted earlier, spread across beats in order
        existing = sorted((case_dir / "frames").glob("frame_*.jpg"))
        if existing and segments:
            for i, seg in enumerate(segments):
                j = min(len(existing) - 1, round(i * (len(existing) - 1) / max(1, len(segments) - 1)))
                frames[seg["id"]] = {"a": ref(existing[j])}
    return frames, strip


def build_doc(case_dir: Path, video: Path | None, threshold: float, embed: bool,
              force: bool, report_path: Path, proxy: bool = True) -> dict:
    analysis = json.loads((case_dir / "analysis.json").read_text(encoding="utf-8"))
    measure = None
    measure_error = ""
    if video:
        try:
            measure = load_or_measure(video, case_dir, threshold, force)
        except (RuntimeError, OSError, subprocess.TimeoutExpired) as exc:
            measure_error = str(exc)
    segments = build_segments(analysis, measure)

    prompts = load_prompts(case_dir)
    stamp_prompts(case_dir, prompts)

    frames, strip = collect_frames(case_dir, video, measure, segments, embed, report_path.parent)
    checks = run_checks(analysis, measure, segments, prompts)
    meta = analysis.get("meta") or {}

    playable = video
    if video and measure and proxy and needs_proxy(measure["probe"]):
        playable = make_proxy(video, case_dir / "report_assets" / "proxy.mp4", measure["probe"]) or video
    return {
        "case_id": case_dir.name,
        "title": meta.get("title") or case_dir.name,
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "video": {
            "src": os.path.relpath(playable, report_path.parent) if playable else "",
            "name": video.name if video else "",
            "proxy": bool(playable and playable != video),
        },
        "analysis": analysis,
        "measure": measure,
        "measure_error": measure_error,
        "params": PARAMS,
        "segments": segments,
        "frames": frames,
        "filmstrip": strip,
        "prompts": prompts,
        "checks": checks,
        "stats": compute_stats(analysis, measure, segments),
        "functions": NARRATIVE_FUNCTIONS,
    }


# --------------------------------------------------------------------------
# HTML rendering: shell + inlined css/js + inlined JSON
# --------------------------------------------------------------------------

def _inline_json(obj) -> str:
    """JSON safe to embed in <script>: escape `</` and `<!--` to avoid early termination."""
    return json.dumps(obj, ensure_ascii=False).replace("<", "\\u003c")


def render_html(doc: dict) -> str:
    tpl = (ASSET_DIR / "template.html").read_text(encoding="utf-8")
    css = (ASSET_DIR / "report.css").read_text(encoding="utf-8")
    js = (ASSET_DIR / "report.js").read_text(encoding="utf-8")
    return (tpl.replace("{{TITLE}}", html.escape(doc["title"]))
               .replace("/*{{CSS}}*/", css)
               .replace("/*{{JS}}*/", js)
               .replace("{{DOC}}", _inline_json(doc)))


def build_report(case_dir: Path, video: Path | None = None, threshold: float | None = None,
                 embed: bool = True, force: bool = False, out: Path | None = None,
                 proxy: bool = True) -> tuple[Path, dict]:
    case_dir = case_dir.resolve()
    if not (case_dir / "analysis.json").exists():
        raise FileNotFoundError(f"{case_dir}/analysis.json not found")
    analysis = json.loads((case_dir / "analysis.json").read_text(encoding="utf-8"))
    video = video.resolve() if video else guess_video(case_dir, analysis)
    report_path = (out or case_dir / "report.html").resolve()
    doc = build_doc(case_dir, video, threshold or PARAMS["scene_threshold"], embed, force, report_path, proxy)
    report_path.write_text(render_html(doc), encoding="utf-8")
    return report_path, doc


def check_summary(doc: dict) -> str:
    counts = {s: sum(1 for c in doc["checks"] if c["status"] == s) for s in ("pass", "warn", "fail", "skip")}
    return f"{counts['pass']} pass · {counts['warn']} warn · {counts['fail']} fail · {counts['skip']} skipped"


def _report_summary(report: Path) -> tuple[dict, str]:
    """Read check counts and prompt format back from a built report's inlined doc."""
    if not report.exists():
        return {}, ""
    m = re.search(r'<script id="doc" type="application/json">(.*?)</script>',
                  report.read_text(encoding="utf-8"), re.S)
    if not m:
        return {}, ""
    try:
        doc = json.loads(m.group(1))
    except json.JSONDecodeError:
        return {}, ""
    counts = {s: 0 for s in ("pass", "warn", "fail", "skip")}
    for c in doc.get("checks") or []:
        counts[c.get("status", "skip")] = counts.get(c.get("status", "skip"), 0) + 1
    pr = doc.get("prompts") or {}
    kind = "" if not pr.get("versions") else "legacy" if pr.get("legacy") else "abc"
    return counts, kind


def _probe_dims(video: Path) -> dict:
    try:
        r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0",
                            "-show_entries", "stream=width,height:format=duration", "-of", "json", str(video)],
                           capture_output=True, text=True, timeout=20)
        j = json.loads(r.stdout or "{}")
        s = (j.get("streams") or [{}])[0]
        w, h = int(s.get("width") or 0), int(s.get("height") or 0)
        return {"duration": round(float((j.get("format") or {}).get("duration") or 0), 1),
                "aspect": ("9:16" if h > w else "16:9" if w > h else "1:1") if w and h else ""}
    except (OSError, ValueError, subprocess.TimeoutExpired, json.JSONDecodeError):
        return {}


def load_goodcases(good_dir: Path, output_root: Path) -> dict:
    """
    goodcase/ holds finished generations worth reusing as playstyle templates:
    videoXX.mp4 + videoXX.md (the prompt that produced it), grouped by goodcase.json.
    """
    if not good_dir.is_dir():
        return {"groups": []}
    try:
        meta = json.loads((good_dir / "goodcase.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        meta = {}
    stems = sorted({p.stem for p in good_dir.iterdir() if p.suffix in (".mp4", ".mov", ".md")})
    hashes: dict[str, str] = {}

    def item(stem: str, label: str) -> dict:
        vid = next((good_dir / f"{stem}{ext}" for ext in (".mp4", ".mov") if (good_dir / f"{stem}{ext}").exists()), None)
        md = good_dir / f"{stem}.md"
        prompt = md.read_text(encoding="utf-8").strip() if md.exists() else ""
        ts = max([p.stat().st_mtime for p in (vid, md) if p and p.exists()] or [0])
        dup = ""
        if vid:
            st = vid.stat()
            sig = f"{st.st_size}"
            if sig in hashes:
                with open(vid, "rb") as f1, open(good_dir / hashes[sig], "rb") as f2:
                    if hashlib.sha1(f1.read()).digest() == hashlib.sha1(f2.read()).digest():
                        dup = hashes[sig]
            else:
                hashes[sig] = vid.name
        return {"stem": stem, "label": label or stem,
                "video": os.path.relpath(vid, output_root) if vid else "",
                "prompt": prompt, "chars": len(prompt), "dup_of": dup,
                "updated_at": _fmt_time(ts) if ts else "", "updated_ts": int(ts),
                **(_probe_dims(vid) if vid else {})}

    groups, used = [], set()
    for g in meta.get("groups") or []:
        items = [item(i["stem"], i.get("label", "")) for i in g.get("items") or [] if i.get("stem") in stems]
        used.update(i["stem"] for i in items)
        if items:
            groups.append({**{k: g.get(k) for k in ("id", "title", "playstyle", "tags", "why", "extend")},
                           "items": items, "updated_ts": max(i["updated_ts"] for i in items)})
    rest = [item(s, s) for s in stems if s not in used]
    if rest:
        groups.append({"id": "unsorted", "title": "未归类", "playstyle": "在 goodcase.json 里登记后会归到对应玩法",
                       "tags": [], "why": "", "extend": [], "items": rest,
                       "updated_ts": max(i["updated_ts"] for i in rest)})
    for g in groups:
        g["updated_at"] = _fmt_time(g["updated_ts"])
    return {"groups": groups}


def build_goodcase(output_root: Path) -> tuple[Path | None, int]:
    output_root = output_root.resolve()
    data = load_goodcases(output_root.parent / "goodcase", output_root)
    if not data["groups"]:
        return None, 0
    tpl = (ASSET_DIR / "goodcase.html").read_text(encoding="utf-8")
    css = (ASSET_DIR / "report.css").read_text(encoding="utf-8")
    out = output_root / "goodcase.html"
    out.write_text(tpl.replace("/*{{CSS}}*/", css).replace("{{DATA}}", _inline_json(data)), encoding="utf-8")
    return out, sum(len(g["items"]) for g in data["groups"])


def build_index(output_root: Path) -> Path:
    """Gallery page linking every case report under output_root."""
    output_root = output_root.resolve()
    cases = []
    for d in sorted(p for p in output_root.iterdir() if p.is_dir()):
        aj = d / "analysis.json"
        if not aj.exists():
            continue
        try:
            a = json.loads(aj.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        meta, summary = a.get("meta") or {}, a.get("summary") or {}
        cover = ""
        for cand in [d / "report_assets" / "B01a.jpg", *sorted((d / "frames").glob("frame_*.jpg"))[:1]]:
            if cand.exists():
                cover = os.path.relpath(cand, output_root)
                break
        m = {}
        if (d / "measure.json").exists():
            try:
                m = json.loads((d / "measure.json").read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                m = {}
        thumbs = [os.path.relpath(p, output_root) for p in sorted((d / "report_assets").glob("B*a.jpg"))[:8]]
        mtime = aj.stat().st_mtime
        # "0919_001" / "0607_003_pub" -> batch 0919, seq 1; other names fall back to file time
        dm = re.match(r"^(\d{4})_(\d+)", d.name)
        batch = dm.group(1) if dm else datetime.fromtimestamp(mtime).strftime("%m%d")
        seq = int(dm.group(2)) if dm else 0
        checks, prompt_kind = _report_summary(d / "report.html")
        updated = case_updated_ts(d) or mtime
        cases.append({
            "id": d.name,
            "title": meta.get("title") or d.name,
            "one_sentence": summary.get("one_sentence", ""),
            "duration": (m.get("probe") or {}).get("duration") or meta.get("duration_seconds"),
            "aspect": (m.get("probe") or {}).get("aspect") or meta.get("aspect_ratio", ""),
            "format": meta.get("primary_format", ""),
            "pace": meta.get("pace", ""),
            "shots": len(m.get("shots", [])) or meta.get("estimated_shot_count"),
            "hook": (a.get("viral_mechanics") or {}).get("hook_type", ""),
            "keywords": ((a.get("visual_language") or {}).get("style_keywords") or [])[:4],
            "cover": cover,
            "report": f"{d.name}/report.html" if (d / "report.html").exists() else "",
            "has_prompts": (d / "prompts.md").exists(),
            "status": "pub" if d.name.endswith("_pub") else "del" if d.name.endswith("_del") else "",
            "batch": batch,
            "seq": seq,
            "mtime": int(mtime),
            "updated_at": _fmt_time(updated),
            "updated_ts": int(updated),
            "thumbs": thumbs,
            "checks": checks,
            "prompt_kind": prompt_kind,
        })
    _, good_n = build_goodcase(output_root)
    tpl = (ASSET_DIR / "index.html").read_text(encoding="utf-8")
    css = (ASSET_DIR / "report.css").read_text(encoding="utf-8")
    page = (tpl.replace("/*{{CSS}}*/", css)
               .replace("{{CASES}}", _inline_json({"cases": cases, "goodcase": good_n,
                                                    "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M")})))
    out = output_root / "index.html"
    out.write_text(page, encoding="utf-8")
    return out


def main() -> int:
    import argparse

    p = argparse.ArgumentParser(description="Build an interactive HTML report for analyzed cases")
    p.add_argument("case_dir", nargs="?", help="case directory containing analysis.json")
    p.add_argument("--video", help="source video (default: auto-detect from downloads/)")
    p.add_argument("--threshold", type=float, default=PARAMS["scene_threshold"],
                   help="scene-cut threshold; lower for dark/slow footage (default 0.3)")
    p.add_argument("--link-assets", action="store_true",
                   help="reference keyframes by relative path instead of embedding them")
    p.add_argument("--force", action="store_true", help="ignore measure.json cache")
    p.add_argument("--no-proxy", action="store_true",
                   help="play the source directly instead of a 720p H.264 proxy (HEVC/4K sources)")
    p.add_argument("--all", metavar="OUTPUT_ROOT", help="build every case under OUTPUT_ROOT + index")
    p.add_argument("--index", metavar="OUTPUT_ROOT", help="only rebuild OUTPUT_ROOT/index.html")
    args = p.parse_args()

    if args.index:
        print(f"✅ Index: {build_index(Path(args.index))}")
        return 0
    if args.all:
        root = Path(args.all)
        ok = fail = 0
        for d in sorted(x for x in root.iterdir() if (x / "analysis.json").exists()):
            try:
                _, doc = build_report(d, threshold=args.threshold, embed=not args.link_assets,
                                      force=args.force, proxy=not args.no_proxy)
                ok += 1
                tag = "measured" if doc["measure"] else "no video"
                print(f"  ✓ {d.name} ({tag}) · {check_summary(doc)}")
            except Exception as exc:  # keep batch going; report at the end
                fail += 1
                print(f"  ✗ {d.name}: {exc}", file=sys.stderr)
        print(f"✅ {ok} reports built, {fail} failed. Index: {build_index(root)}")
        return 0 if not fail else 1
    if not args.case_dir:
        p.error("case_dir is required (or use --all / --index)")

    case_dir = Path(args.case_dir)
    path, doc = build_report(case_dir, Path(args.video) if args.video else None, args.threshold,
                             embed=not args.link_assets, force=args.force, proxy=not args.no_proxy)
    print(f"✅ Report: {path}")
    if doc["measure_error"]:
        print(f"⚠️  Measurement failed, report built from analysis only: {doc['measure_error']}")
    elif not doc["measure"]:
        print("⚠️  Source video not found; measured tracks and checks are skipped (use --video)")
    print(f"   checks: {check_summary(doc)}")
    build_index(case_dir.resolve().parent)
    return 0


if __name__ == "__main__":
    sys.exit(main())
