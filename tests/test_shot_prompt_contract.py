"""Tests for the Seedance final prompt composition contract."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from shot_prompt_generator import (
    _extract_continuity_directives,
    _resolve_music_generation_directive,
    _resolve_realism_camera_directive,
    build_single_prompt_user_prompt,
    build_user_prompt,
    render_prompts_md,
)


class TestSeedancePromptContract(unittest.TestCase):
    def setUp(self):
        self.analysis_data = {
            "meta": {
                "title": "contract-test",
                "duration_seconds": 15,
                "aspect_ratio": "16:9",
                "primary_format": "ugc",
            },
            "timeline": [
                {
                    "start": 0,
                    "end": 3,
                    "visual_event": "人物穿过树林",
                    "subject_description": "黑发青年，灰色外套",
                    "subject_action": "快速奔跑，衣摆被风吹动",
                    "camera_action": "低机位跟拍",
                    "camera_details": "中景",
                    "environment_description": "铅笔森林",
                    "audio_event": "脚步声和风声",
                }
            ],
            "visual_language": {
                "realism_level": "photorealistic",
                "camera_equipment_feel": "手机手持",
            },
            "camera_language": {
                "dominant_movement": "手持跟拍",
                "movement_continuity": "全程连续",
            },
            "audio_visual_sync": {
                "music_genre": "电子乐",
                "beat_impact_on_visuals": "重拍切镜",
                "character_rhythm_sync": "随节拍奔跑",
                "environment_music_elements": "无",
            },
        }

    def assert_contract_present(self, prompt: str):
        self.assertIn("主体：", prompt)
        self.assertIn("场景：", prompt)
        self.assertIn("BGM 默认开启", prompt)
        self.assertIn("具体参考曲目或热梗音乐", prompt)
        self.assertIn("BPM", prompt)
        self.assertIn("Shot 01", prompt)
        self.assertIn("禁止使用 [0-3秒]、0-3s 等时间戳", prompt)
        self.assertIn("720p", prompt)
        self.assertIn("不要上传或引用拼接式分镜故事板", prompt)

    def test_single_prompt_uses_compact_four_part_contract(self):
        prompt = build_single_prompt_user_prompt(self.analysis_data)
        self.assert_contract_present(prompt)
        self.assertNotIn("时间戳分镜法", prompt)
        self.assertIn("目标控制在 400-1000 字符", prompt)

    def test_storyboard_prompt_uses_same_contract(self):
        prompt = build_user_prompt(self.analysis_data)
        self.assert_contract_present(prompt)

    def test_prompt_generation_requests_original_aspect_and_complete_versions(self):
        prompt = build_single_prompt_user_prompt(self.analysis_data)
        self.assertIn("人物参考图画幅必须与原视频一致：16:9", prompt)
        self.assertIn('"prompt_versions"', prompt)
        self.assertIn('"id": "A"', prompt)
        self.assertIn('"id": "B"', prompt)
        self.assertIn('"id": "C"', prompt)
        self.assertIn("不得写“同上/与 A 相同”", prompt)
        self.assertIn("同一人物存在眼镜→无眼镜", prompt)
        self.assertIn("以用户上传的 @图片1 为身份与构图参考", prompt)

    def test_prompts_markdown_groups_character_and_video_by_version(self):
        data = {
            "metadata": {"source_title": "test", "aspect_ratio": "16:9"},
            "prompt_versions": [
                {"id": "A", "name": "A款", "character_prompt": "人物A", "video_prompt": "视频A"},
                {"id": "B", "name": "B款", "character_prompt": "人物B", "video_prompt": "视频B"},
                {"id": "C", "name": "C款", "character_prompt": "人物C", "video_prompt": "视频C"},
            ],
        }
        markdown = render_prompts_md(data)
        self.assertEqual(markdown.count("### 人物参考图 Prompt"), 3)
        self.assertEqual(markdown.count("### 视频 Prompt"), 3)
        self.assertLess(markdown.index("人物A"), markdown.index("视频A"))
        self.assertLess(markdown.index("视频A"), markdown.index("## 版本 B"))

    def test_prompts_markdown_renders_each_outfit_reference(self):
        data = {
            "metadata": {"source_title": "transform", "aspect_ratio": "9:16"},
            "prompt_versions": [
                {
                    "id": "A",
                    "name": "变装",
                    "character_prompt": "兼容人物一",
                    "character_prompts": [
                        {"label": "装扮一（生成 @图片1）", "prompt": "人物一"},
                        {
                            "label": "装扮二（上传 @图片1 后生成 @图片2）",
                            "prompt": "以 @图片1 锁定同一人物，生成人物二",
                        },
                    ],
                    "video_prompt": "同时引用 @图片1 和 @图片2",
                }
            ],
        }

        markdown = render_prompts_md(data)

        self.assertIn("### 人物参考图 Prompt 1 · 装扮一（生成 @图片1）", markdown)
        self.assertIn(
            "### 人物参考图 Prompt 2 · 装扮二（上传 @图片1 后生成 @图片2）",
            markdown,
        )
        self.assertLess(markdown.index("人物一"), markdown.index("人物二"))
        self.assertLess(markdown.index("人物二"), markdown.index("### 视频 Prompt"))

    def test_ugc_audio_rule_generates_specific_bgm_by_default(self):
        directive = _resolve_realism_camera_directive(self.analysis_data)
        self.assertIn("BGM + 音效（默认启用", directive)
        self.assertIn("具体参考曲目/热梗音乐", directive)
        self.assertIn("BPM", directive)
        self.assertNotIn("BGM 留给后期", directive)

    def test_music_can_be_explicitly_disabled(self):
        directive = _resolve_music_generation_directive(
            self.analysis_data,
            music_mode="off",
        )
        self.assertIn("用户明确要求关闭 BGM", directive)
        self.assertIn("音乐：不要生成任何背景音乐，只生成对应的音效", directive)

        prompt = build_single_prompt_user_prompt(
            self.analysis_data,
            music_mode="off",
        )
        self.assertIn("用户明确要求关闭 BGM", prompt)

    def test_rigged_surveillance_forces_single_take_physics(self):
        surveillance_data = {
            **self.analysis_data,
            "meta": {
                **self.analysis_data["meta"],
                "title": "门载监控回家",
                "primary_format": "固定监控",
            },
            "camera_language": {
                "dominant_movement": "门载猫眼摄像头固定在门扇",
                "movement_continuity": "全程不停机",
            },
            "timeline": [
                {
                    "visual_event": "女生拿起快递，腾出右手用钥匙开门",
                    "camera_action": "固定猫眼监控",
                }
            ],
        }
        directive = _resolve_realism_camera_directive(surveillance_data)
        self.assertIn("刚性安装的监控", directive)
        self.assertIn("不用 Shot 编号", directive)
        self.assertIn("不切镜、不转场、不跳时、不重置构图", directive)
        self.assertIn("向屋内开启", directive)
        self.assertIn("围绕固定合页", directive)
        self.assertIn("逐渐扫过自家门框内侧", directive)
        self.assertIn("不是镜头独立向前推进", directive)
        self.assertIn("画面近端盲区", directive)
        self.assertIn("远端邻居门", directive)
        self.assertIn("绝不能切成门外第三个人向屋内拍", directive)
        self.assertIn("不看镜头、不对镜头互动", directive)
        self.assertIn("持物连续性", directive)
        self.assertIn("转移到左前臂并夹紧身体", directive)
        self.assertIn("多件重物应先平稳放地", directive)
        self.assertNotIn("15 秒内自然快切 3-4 个不同镜头", directive)
        self.assertNotIn("人物与镜头有直接互动", directive)

        prompt = build_single_prompt_user_prompt(surveillance_data)
        self.assertIn("单段「连续动作流程：」", prompt)
        self.assertIn("禁止独立运镜和第三人称机位", prompt)

        continuity = _extract_continuity_directives(surveillance_data)
        self.assertIn("固定监控连续性", continuity)
        self.assertIn("固定地标的屏幕移动方向", continuity)
        self.assertNotIn("Orbit持续旋转中", continuity)


if __name__ == "__main__":
    unittest.main()
