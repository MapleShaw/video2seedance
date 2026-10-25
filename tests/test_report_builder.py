"""
test_report_builder.py

Unit tests for the pure (no ffmpeg) parts of report_builder:
shot building, curve medians, onset/sync heuristics, prompt parsing,
camera-claim classification and the reconciliation checks.
"""

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from report_builder import (  # noqa: E402
    PARAMS,
    _inline_json,
    aspect_of,
    build_segments,
    build_shots,
    camera_claim,
    detect_onsets,
    find_prompt_timestamps,
    median_in,
    parse_legacy_prompts,
    parse_prompts_md,
    ratio_of,
    render_html,
    run_checks,
    sync_rate,
)


def make_measure(duration=10.0, cuts=(), motion=None, onsets=()):
    hz = PARAMS["motion_hz"]
    shots = build_shots(list(cuts), duration, PARAMS["min_shot_seconds"])
    values = motion if motion is not None else [5.0] * int(duration * hz + 1)
    for s in shots:
        s["motion"] = median_in({"hz": hz, "values": values}, s["start"], s["end"])
    return {
        "probe": {"duration": duration, "fps": 30, "width": 720, "height": 1280, "aspect": "9:16",
                  "video_codec": "h264", "audio_codec": "aac", "has_audio": True},
        "shots": shots,
        "motion": {"hz": hz, "values": values},
        "brightness": {"hz": hz, "values": []},
        "audio": {"hz": 20, "values": []},
        "onsets": list(onsets),
        "sync": sync_rate([s["start"] for s in shots[1:]], list(onsets), PARAMS["sync_tolerance"]),
        "params": PARAMS,
        "palette": [],
    }


def make_analysis(**overrides):
    a = {
        "meta": {"title": "t", "duration_seconds": 10.0, "aspect_ratio": "9:16", "estimated_shot_count": 1},
        "summary": {"one_sentence": "x"},
        "viral_mechanics": {"hook_type": "x"},
        "transferable_pattern": {"abstract_pattern": "x"},
        "seedance_translation": {"recommended_mode": "pure_text"},
        "camera_language": {"dominant_movement": "固定机位"},
        "timeline": [
            {"start": 0, "end": 5, "camera_action": "固定机位", "narrative_function": "hook", "attention_level": 4},
            {"start": 5, "end": 10, "camera_action": "固定机位", "narrative_function": "payoff", "attention_level": 5},
        ],
    }
    for k, v in overrides.items():
        a[k] = v
    return a


def check(checks, cid):
    return next(c for c in checks if c["id"] == cid)


class TestShotsAndCurves(unittest.TestCase):
    def test_build_shots_merges_short_fragments(self):
        shots = build_shots([0.1, 2.0, 2.1, 5.0, 9.9], 10.0, 0.3)
        self.assertEqual([s["start"] for s in shots], [0.0, 2.0, 5.0])
        self.assertEqual(shots[-1]["end"], 10.0)
        self.assertAlmostEqual(sum(s["seconds"] for s in shots), 10.0, places=2)

    def test_build_shots_one_take(self):
        shots = build_shots([], 7.5, 0.3)
        self.assertEqual(len(shots), 1)
        self.assertEqual(shots[0]["seconds"], 7.5)

    def test_median_trims_cut_spikes(self):
        values = [100.0] * 3 + [2.0] * 15 + [100.0] * 3  # spikes at both edges
        self.assertEqual(median_in({"hz": 10, "values": values}, 0.0, 2.0), 2.0)

    def test_median_handles_empty(self):
        self.assertIsNone(median_in({"hz": 10, "values": []}, 0, 1))
        self.assertIsNone(median_in({"hz": 10, "values": [1, 2]}, 1, 1))

    def test_onsets_and_sync(self):
        vals = [-40.0] * 20
        vals[5] = -20.0
        vals[12] = -18.0
        onsets = detect_onsets({"hz": 20, "values": vals}, 4.5)
        self.assertEqual(onsets, [0.25, 0.6])
        s = sync_rate([0.3, 2.0], onsets, 0.12)
        self.assertEqual(s["rate"], 0.5)
        self.assertIsNone(sync_rate([], onsets, 0.12)["rate"])


class TestParsing(unittest.TestCase):
    def test_aspect(self):
        self.assertEqual(aspect_of(720, 1280), "9:16")
        self.assertEqual(aspect_of(2160, 3840), "9:16")
        self.assertEqual(aspect_of(1162, 720), "16:10")
        self.assertAlmostEqual(ratio_of("581:360（1162x720，横屏）"), 581 / 360)
        self.assertIsNone(ratio_of("竖屏"))

    def test_camera_claim_with_negation(self):
        self.assertEqual(camera_claim("固定机位，不推拉、不摇移"), "static")
        self.assertEqual(camera_claim("手持跟拍，缓慢推近"), "moving")
        self.assertEqual(camera_claim("超近景"), "")

    def test_prompts_md(self):
        md = (
            "# Case · A/B/C\n> note line\n\n## 版本 A · one\n### 人物参考图 Prompt\nimg A\n"
            "### 视频 Prompt\n```\n主体：@主体\nShot 01 | 0-3秒 push\n```\n## 版本 B · two\n### 视频 Prompt\nvid B\n"
        )
        p = parse_prompts_md(md)
        self.assertEqual(p["title"], "Case · A/B/C")
        self.assertEqual(p["intro"], "note line")
        self.assertEqual([v["title"] for v in p["versions"]], ["版本 A · one", "版本 B · two"])
        self.assertEqual(p["versions"][0]["blocks"][1]["body"], "主体：@主体\nShot 01 | 0-3秒 push")
        hits = find_prompt_timestamps(p)
        self.assertEqual(len(hits), 1)
        self.assertIn("0-3秒", hits[0])

    def test_inline_json_cannot_close_script(self):
        s = _inline_json({"x": "</script><!-- a"})
        self.assertNotIn("<", s)
        self.assertEqual(json.loads(s)["x"], "</script><!-- a")


class TestChecks(unittest.TestCase):
    def test_clean_case_passes(self):
        a = make_analysis()
        m = make_measure(motion=[0.5] * 101)
        checks = run_checks(a, m, build_segments(a, m), None)
        for cid in ("timeline", "fields", "duration", "aspect", "shots", "oneshot", "camera"):
            self.assertEqual(check(checks, cid)["status"], "pass", cid)

    def test_oneshot_claim_vs_cuts(self):
        a = make_analysis()
        m = make_measure(cuts=[3.0, 6.0])
        c = check(run_checks(a, m, build_segments(a, m), None), "oneshot")
        self.assertEqual(c["status"], "warn")
        self.assertIn("3.00s", c["detail"])

    def test_claimed_movement_but_still(self):
        tl = [{"start": 0, "end": 10, "camera_action": "缓慢推近 + 环绕跟拍", "narrative_function": "hook"}]
        a = make_analysis(timeline=tl, camera_language={})
        m = make_measure(motion=[0.2] * 101)
        c = check(run_checks(a, m, build_segments(a, m), None), "camera")
        self.assertEqual(c["status"], "warn")
        self.assertEqual(c["refs"], ["B01"])

    def test_timeline_gap_and_duration_mismatch(self):
        tl = [{"start": 0, "end": 3}, {"start": 5, "end": 10}]
        a = make_analysis(timeline=tl)
        a["meta"]["duration_seconds"] = 15
        m = make_measure()
        checks = run_checks(a, m, build_segments(a, m), None)
        self.assertEqual(check(checks, "timeline")["status"], "warn")
        self.assertEqual(check(checks, "duration")["status"], "warn")

    def test_without_video_measured_checks_skip(self):
        a = make_analysis()
        checks = run_checks(a, None, build_segments(a, None), None)
        for cid in ("duration", "aspect", "shots", "oneshot", "camera"):
            self.assertEqual(check(checks, cid)["status"], "skip", cid)

    def test_legacy_prompt_files_not_held_to_contract(self):
        a = make_analysis()
        p = parse_legacy_prompts([("variant_prompts.md", "## 变体 ①\n```\n0-3秒 something\n```\n")])
        c = check(run_checks(a, None, [], p), "prompt_ts")
        self.assertEqual(c["status"], "skip")


SHOT_MD = """# 分镜
## 🎭 角色参考图
### 短发女生  `char_A`  主角  出现于 Shot 1
```
CHAR PROMPT
```
## 🎬 Seedance 视频提示词
```
VIDEO PROMPT
```
## 变体方向
### 街舞潮酷风 — 换成街舞
"""

VARIANT_MD = """# 变体
## 第 1 步 · 人物参考图 Prompt
**中文版：**
```
SHARED CHAR
```
**过审收敛版】：**
```
只替换服装段落：穿白色T恤，其余不变
```
## 第 2 步 · 视频
### 版本 A · 默认款
```
VIDEO A
```
### 版本 B · 反差款
```
VIDEO B
```
"""


class TestLegacyPrompts(unittest.TestCase):
    def test_shot_prompts_only_keeps_original_and_directions(self):
        p = parse_legacy_prompts([("shot_prompts.md", SHOT_MD)])
        self.assertTrue(p["legacy"])
        self.assertEqual(len(p["versions"]), 1)
        titles = [b["title"] for b in p["versions"][0]["blocks"]]
        self.assertEqual(titles[0], "短发女生 · 人物参考图")
        self.assertEqual([b["body"] for b in p["versions"][0]["blocks"]], ["CHAR PROMPT", "VIDEO PROMPT"])
        self.assertEqual(p["directions"][0]["title"], "街舞潮酷风 — 换成街舞")

    def test_versions_get_shared_character_and_partial_flag(self):
        p = parse_legacy_prompts([("shot_prompts.md", SHOT_MD), ("variant_prompts.md", VARIANT_MD)])
        tabs = {v["title"]: v for v in p["versions"]}
        self.assertIn("版本 A · 默认款", tabs)
        bodies = [b["body"] for b in tabs["版本 B · 反差款"]["blocks"]]
        self.assertEqual(bodies[0], "SHARED CHAR")
        self.assertEqual(bodies[-1], "VIDEO B")
        partial = [b for b in tabs["版本 A · 默认款"]["blocks"] if b["partial"]]
        self.assertEqual(len(partial), 1)
        self.assertEqual(tabs["版本 A · 默认款"]["blocks"][-1]["title"], "视频 Prompt")
        # full variants exist, so the one-line ideas from shot_prompts.md are dropped
        self.assertEqual(p["directions"], [])


class TestRender(unittest.TestCase):
    def test_render_inlines_assets_and_escapes(self):
        a = make_analysis()
        a["meta"]["title"] = "<b>t</b>"
        m = make_measure()
        doc = {
            "case_id": "c", "title": a["meta"]["title"], "generated_at": "now",
            "video": {"src": "", "name": "", "proxy": False}, "analysis": a, "measure": m,
            "measure_error": "", "params": PARAMS, "segments": build_segments(a, m), "frames": {},
            "filmstrip": [], "prompts": None, "checks": [], "stats": {"duration": 10, "beats": 2}, "functions": [],
        }
        out = render_html(doc)
        self.assertNotIn("{{", out)
        self.assertNotIn("/*{{", out)
        self.assertIn("<title>&lt;b&gt;t&lt;/b&gt; · 拆解报告</title>", out)
        self.assertIn("renderTracks", out)  # report.js inlined
        self.assertIn(".tracks-canvas", out)  # report.css inlined

    def test_build_report_without_video(self):
        from report_builder import build_report
        with tempfile.TemporaryDirectory() as tmp:
            case = Path(tmp) / "zz_case"
            case.mkdir()
            (case / "analysis.json").write_text(json.dumps(make_analysis()), encoding="utf-8")
            path, doc = build_report(case)
            self.assertTrue(path.exists())
            self.assertIsNone(doc["measure"])
            self.assertEqual(len(doc["segments"]), 2)


if __name__ == "__main__":
    unittest.main()
