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

# 自动加载项目根目录 .env
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent.parent / ".env")
except ImportError:
    pass

from validation import (
    validate_shot_prompts,
    validate_character_consistency,
    validate_style_anchor_compliance,
    validate_7dimension_completeness,
    detect_character_drift,
)
from style_validation import (
    validate_style_anchor_prefix,
    validate_platform_compliance,
    compare_style_consistency,
)


# ─── Seedance Skill 检测 & 读取 ─────────────────────────────────────────────

SKILL_SEARCH_PATHS = [
    Path.home() / ".openclaw/workspace/skills/seedance-prompt/SKILL.md",
    Path("/usr/lib/node_modules/openclaw/skills/seedance-prompt/SKILL.md"),
]


def load_seedance_skill() -> str | None:
    """
    尝试加载 SKILL.md 内容。找到返回文本，找不到返回 None。
    
    查找顺序：
    1. 环境变量 SEEDANCE_SKILL_PATH（优先级最高，支持 .env 配置）
    2. 项目根目录 SKILL.md（确保当前项目规则优先于外部旧副本）
    3. 内置搜索路径（OpenClaw workspace / 系统级）
    """
    # 优先检查环境变量指定的路径
    env_path = os.environ.get("SEEDANCE_SKILL_PATH")
    if env_path:
        p = Path(env_path).expanduser()
        if p.exists():
            print(f"[shot_prompt_generator] ✅ 从 SEEDANCE_SKILL_PATH 加载: {p}")
            return p.read_text(encoding="utf-8")
        else:
            print(f"[shot_prompt_generator] ⚠️ SEEDANCE_SKILL_PATH 指向的文件不存在: {p}")

    # 优先使用当前项目自带规则，避免外部 Skill 旧副本覆盖本项目约定
    local_skill = Path(__file__).parent.parent / "SKILL.md"
    if local_skill.exists():
        print(f"[shot_prompt_generator] ✅ 检测到项目内 SKILL.md: {local_skill}")
        return local_skill.read_text(encoding="utf-8")

    for p in SKILL_SEARCH_PATHS:
        if p.exists():
            print(f"[shot_prompt_generator] ✅ 检测到 Seedance skill: {p}")
            return p.read_text(encoding="utf-8")

    print("[shot_prompt_generator] ⚠️ 未检测到 Seedance SKILL.md，LLM 将使用内置知识生成")
    return None


# ─── LLM 调用 ───────────────────────────────────────────────────────────────

DEFAULT_BASE_URL = "https://zenmux.ai/api/v1"
DEFAULT_MODEL = "anthropic/claude-sonnet-4.6"


CASE_SPECIFIC_GUIDANCE = {
    "0711_001": dedent("""
    【用户案例约束·0711_001·车内驾驶过程混剪】
    这是短时长的驾驶过程混剪，不是上车流程教学：用 4-5 个短促独立镜头，只保留进入驾驶状态、道路行驶、红绿灯短暂停车或最终停车的大节奏，不逐项交代开门、迈腿、系安全带、挂挡等细节。镜头可以跳切，不要求动作连续，主体始终是人：任何车外镜头都必须同时看到人物的脸和大部分身材，禁止只拍车、车轮、手或方向盘的无人物特写。交替展示人物驾驶时的正面/侧面、人物与车的全身关系、窗外流动道路和一次自然靠近镜头的近脸互动，再切回行驶过程。人物视线主要落在道路和红绿灯上，只偶尔短暂看镜头；动作有呼吸、重心变化和随手调整，不能像按步骤演示。环境、人物和装扮以参考图为准，不重复描述服装和外貌。音乐参考 2026 年 7 月公开热榜候选《奔腾》—周深的推进感，但只生成同类原创，不照搬旋律；保留轻微焦点偏离、手机抖动、动态模糊、动作边缘软化、暗部细小随机噪点、自动曝光微漂移、降噪和平台压缩。
    """),
    "0711_002": dedent("""
    【用户案例约束·0711_002·夜间音乐现场混剪】
    这是约 4 个镜头的音乐节混剪，至少包含人物正面和背面/斜后方视角。背景不要塞满人，人物过多时主动减少到少量有层次的路人。每个路人以不同节奏做随意小动作：聊天时转头或抬杯、看舞台点头、经过时自然避让、短暂举手机后放下；允许个别人几乎不动，但不能所有人同时动、同时停或整齐重复。主角每个镜头使用不同动作和状态，例如捋头发、自然转身、看舞台、随音乐摆肩、换重心、整理包带或短暂回眸，不循环同一手势。全程正常实时速度，只用硬切和重拍强调节奏，不使用慢动作、升格或变速。人物自然眨眼，视线在舞台、路人和镜头之间转移。音乐参考 2026 年 7 月公开热榜候选《枪火》—老舅的强节奏感，但只生成适合音乐节的原创同类版本；几乎不用闪光灯，依靠红紫蓝氛围光。保留低照度手机动态模糊、轻微焦点偏离、自动曝光漂移、细小随机噪点、降噪和平台压缩。
    """),
    "0711_003": dedent("""
    【用户案例约束·0711_003·海外日常跟拍换装混剪】
    只使用一张人物参考图锁定同一人物，其余服装变化直接写进视频 prompt，不要求多张人物参考图。视频表现中国留学生在美国日常生活中的自然跟拍：去上课、走在街区、买咖啡、经过校园/地铁口、去海边或回到住处等城市片段。镜头方向自然交替：镜头跟在人物后面，人物向前走；或镜头在人物前面向后退，人物朝镜头方向走；也可偶尔从侧面记录经过。不要每个镜头都让人物面朝镜头倒退走。不同镜头自然切换服装、表情和手部动作，例如看路、看远处、微笑、若有所思、拿咖啡、背包、整理头发、抬手挡风或触碰栏杆，动作像朋友随手跟拍而不是时装展示。保持同一人物身份一致，换装和场景用自然硬切或音乐重拍衔接；保留手持晃动、焦点迟滞、动态模糊、细小随机噪点、自动曝光微漂移和平台压缩，禁止商业 Lookbook。
    """),
    "0711_004": dedent("""
    【用户案例约束·0711_004·机舱行李架一镜到底】
    必须是一镜到底、单一连续机位，不切镜、不转场、不跳时、不重置构图。场景和人物形象完全以参考图为准，视频 prompt 不要重复服装和外貌设定。连续动作只需自然表现人物站起、从座位上方行李架取下物品、关好行李架并坐回原位；视线专注于行李架和物品，人物自然眨眼、呼吸、调整重心，不要写成僵硬的流程演示。镜头只做小幅连续跟随以保持人物、脸和整体身材在画面内，不改变机位。行李架必须位于对应座位排上方，手与物品、舱门始终有真实接触。背景乘客可有轻微翻页、调整耳机或看窗外等自然小动作，不要全部静止。音乐参考 2026 年 7 月公开热榜候选《那天下雨了》—周杰伦的轻松流动感，但只生成同类原创旅行 Pop；保留轻微焦点偏离、动作模糊、暗部细小随机噪点、自动曝光微漂移、降噪和平台压缩。
    """),
    "0711_005": dedent("""
    【用户案例约束·0711_005·天台律动一镜到底】
    必须是一镜到底，固定机位，镜头位置、焦段和背景构图不变，不切镜、不转场、不推拉；景别变化只能来自人物自己走近或走远。人物从近景开始，先自然眨眼、看向镜头、俏皮轻笑、捋发或轻触衣物，随后主动向后走远并逐渐过渡到全身；远景阶段加入更有幅度但仍真实的轻跳、抖腿、摆肩、摆臂、换重心和小步舞，不要从头到尾只有走路。动作有呼吸、惯性和表情变化，不能像固定模板。音乐参考 2026 年 7 月公开热榜候选《枪火》—老舅的强鼓点传播感，但只生成适合舞蹈的原创 Dance-Pop/Bounce House 版本，BPM 105-122；禁止纯 chill、慢动作、升格、机械手势舞和逐帧摆 pose。环境与人物以参考图为准，不重复长篇描述。保留轻微焦点偏离、动态模糊、动作边缘软化、细小随机噪点、自动曝光微漂移和手机压缩。
    """),
    "0711_006": dedent("""
    【用户案例约束·0711_006·牵手跟行一镜到底】
    必须是一镜到底，不切镜、不转场、不跳时。镜头外伸入一只手，与人物的手自然扣住并带着人物向前走；手部接触、手臂方向和身体重心连续。音乐不要柔和慢拍，参考 2026 年 7 月公开热榜候选《奔腾》—周深的推进感，但只生成同类原创 Bounce House/流行舞曲，BPM 112-126。人物自然眨眼，视线在镜头、行进方向和街道之间转移，边走边有轻笑、回望和手臂反应。途中安排不规则的牵手互动：先轻轻拉近一步，再自然扯远半步，随后人物回头靠近、牵着的手轻晃后继续前行；互动要有随机性和呼吸感，不得像固定两拍循环，也不能突然拽动、失衡或夸张甩臂。拍摄者向后退，人物逐渐靠近并自然进入脸部近景，不突然怼脸或变形。环境、人物和动作基于参考图，不重复长篇服装描述。保留真实手持晃动、轻微焦点偏离、动态模糊、动作软化、细小随机噪点、自动曝光微漂移和平台压缩。
    """),
    "0711_007": dedent("""
    【用户案例约束·0711_007·健身房环绕一镜到底】
    必须是一镜到底：用明显更快、更利落但平滑的连续升镜完成从脚部到头部的完整环绕，不在脚部停留太久，也不拖成慢动作。看到脸后，立即连续轻微拉远展示全身/近全身，人物依次自然换重心、整理头发、看向镜头后移开视线看镜面、轻笑、摆肩或抬手做一个俏皮小动作；不能始终固定表情和站姿。全程不切镜、不转场、不突然变焦，不做敏感部位特写。健身房环境和人物形象以参考图为准，视频 prompt 不重复长篇服装外貌描述。音乐参考 2026 年 7 月公开热榜候选《枪火》—老舅的冲击力，但只生成同类原创健身电子舞曲，BPM 108-122；升镜、环绕和后段展示随鼓点推进但不切镜。保留手机轻微焦点偏离、动态模糊、动作软化、细小随机噪点、自动曝光微漂移和平台压缩。
    """),
    "0711_008": dedent("""
    【用户案例约束·0711_008·双人异域舞一镜到底】
    必须是一镜到底，不切镜、不转场。开场只保留很短的不同步铺垫：两人用不同表情和小动作建立节奏后，立即用一个明确重拍进入同步的中东/异域风情双人舞，不能让前段拖沓。两人的动作同步但不要机械复制，保留细微错拍、呼吸停顿和个人差异。眼神有生命力：自然眨眼，视线在镜头、彼此、远处环境和地面之间切换，偶尔清晰看向镜头后移开。鞋子必须与各自参考服装一致，使用异域风格的软皮尖头鞋、绣花短靴或装饰性舞鞋，不得出现现代运动鞋、跑鞋或普通休闲鞋。环境、人物妆造、服装与构图以参考图为准，视频 prompt 不重复外貌服装。音乐参考 2026 年 7 月公开热榜候选《龙耀华夏》—龙友林的热度与强鼓点传播感，但只生成同类原创中东异域舞曲，BPM 100-116，使用 darbuka 手鼓、riq 铃鼓、乌德琴和短促拍手；叠加风声、脚步和布料摩擦。保留手机轻微焦点偏离、动态模糊、动作软化、细小随机噪点、自动曝光微漂移和平台压缩。
    """),
}


def _resolve_case_guidance(analysis_data: dict, case_id: str | None = None) -> str:
    """根据显式 case_id 或 analysis.json 的标题/来源识别 case 级约束。"""
    meta = analysis_data.get("meta", {})
    candidates = (
        str(case_id or ""),
        str(meta.get("title", "")),
        str(meta.get("source_title", "")),
        str(analysis_data.get("source_title", "")),
    )
    for case_id, guidance in CASE_SPECIFIC_GUIDANCE.items():
        if any(case_id in candidate for candidate in candidates):
            return guidance
    return ""


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
        max_tokens=32000,
        temperature=0.7,
    )
    return response.choices[0].message.content


# ─── Prompt 构建 ────────────────────────────────────────────────────────────

def build_system_prompt(skill_content: str | None) -> str:
    """构建 system prompt，包含 SKILL.md 规范（如果有的话）。"""
    base = dedent("""\
    你是 Seedance 2.0（即梦）分镜提示词专家。

    你的任务：
    根据视频分析结果（JSON），生成完整的生产资料包：
    A) 角色参考图 prompt（character_sheets）— 为片中每个独立角色生成主体参考图提示词
    B) 单张场景参考图 prompt（scene_reference）— 锁定环境以及主体与环境的比例关系
    C) 视频 prompt（single_prompt 或 shots）— 采用主体/场景/音乐/Shot 编号四段式
    D) 首帧图 prompt（first_frame_prompt）— 仅在复杂镜头确实需要时提供，不得拼成分镜故事板

    这些 prompt 共同定义整部片子的视觉基调，必须高质量、可直接使用。

    ═══════════════════════════════════════════
    零、忠实还原原则（最高优先级，统领一切生成内容）
    ═══════════════════════════════════════════

    所有角色图、首帧图、分镜 prompt 必须忠实还原 analysis.json 中描述的视觉状态。
    严禁任何方向的"默认美化"或"默认丑化"：
    - 如果原视频角色衣衫褴褛、满身血污——必须如实描述破损和血污
    - 如果原视频角色衣着华丽、干净整洁——也必须如实描述华丽和整洁
    - 如果原视频是残破恐怖风格——所有角色的服饰、道具、环境都必须带有对应的陈旧、破损、诡异质感
    - 如果原视频是精致现代风格——所有角色也必须保持干净精致
    - 核心原则：所见即所写，不添加、不省略、不美化、不丑化

    如果 analysis.json 中提供了 visual_language.global_style_direction 字段，
    这就是整部片子的视觉基调声明——所有角色图、首帧图、分镜 prompt 都必须严格服从此基调，
    任何单个镜头的风格描述都不能脱离此基调。

    ═══════════════════════════════════════════
    一、角色参考图（character_sheets）—— 整部片子的视觉锚点
    ═══════════════════════════════════════════

    为片中每个有辨识度的角色（包括非人类角色、生物、机甲等）生成独立的角色参考图 prompt。
    这些图将用于：1) 给即梦的"参考图"功能做角色一致性锚定 2) 给首帧图做角色参考

    核心原则：角色图 prompt 必须严格基于 analysis.json 中 timeline 各条的 subject_description 还原，
    禁止自行想象或添加视频中没有的元素。宁可少写一个细节，也不要编造一个错误的细节。

    角色图 prompt 必须按以下顺序描述：
    - 构图指令：视角(正面/3/4侧面/侧面) + 景别(半身/全身)，背景(纯色/简洁)，角色居中
      注意还原视频中角色最具辨识度的典型角度
    - ⭐ 画幅比：角色参考图统一使用 9:16 竖版构图，prompt 开头必须写明"9:16竖版构图"
    - 风格锚定：与视频整体风格严格一致（写实→写实，3D→3D，不能跑偏）
      * 风格锚定细分：
        · 真人写实 → "写实人像摄影风格，自然皮肤瑕疵可见"
        · 高端CG（像真人但是渲染的）→ "超写实CG角色设计，毛孔级细节"
        · 3A游戏风格 → "UE5超写实3D渲染风格"
        · 动漫/国漫 → 对应的动画渲染风格
        绝不能把"高端CG写实渲染"和"UE5游戏引擎风格"混为一谈
    - 面部五官（从 subject_description 提取，逐项还原，不要概括）：
      * 脸型轮廓（如"瓜子脸线条锐利"而非泛泛的"精致面容"）
      * 眼型+眼神（如"丹凤眼眼尾上挑，眼神妖媚中带危险感"，不要写成"sharp eyes"）
      * 眉形（如"细长柳叶眉微挑"）
      * 鼻型（如"高挺鼻梁"）
      * 唇形+唇色（如"饱满红唇，唇色深红如血"，不要随意降低饱和度写成"淡粉"）
      * 肤色+肤质（如"白皙近乎苍白，可见自然皮肤纹理"）
      * 表情/神态方向（如"微微低头侧目的妖魅感"，这决定整张图的气质，非常关键）
    - 发型发色：发色 + 长度 + 具体造型 + 特殊状态（湿/飘散/结霜/沾血），必须具体
    - 头饰/装饰品（很多角色的核心辨识度就在头饰，不能遗漏）：
      * 类型+材质（金属头冠/骨质犄角/竹编斗笠/宝石链饰等）
      * 佩戴位置和造型
      * 附属装饰元素（如"链条从头冠垂落至额前""角根部缠绕冰晶"）
    - 服装（从上到下逐件描述，不能笼统写"穿着XX"）：
      * 领口/开合程度（高领包裹 vs 低胸露肩 vs 露背 vs 一字肩，这直接决定画面效果，必须忠实还原）
      * 每件衣物：材质+颜色+款式（如"白色薄纱内衫，外披蓬松白色兽毛大氅"）
      * 层叠关系和破损/污渍状态
      * ⭐ 新旧状态（崭新/半旧/陈旧/破旧/战损）——必须与 subject_description 中的描述一致，不能默认美化
      * ⭐ 污渍/痕迹（血污/泥土/水渍/灰尘/锈迹等——有什么写什么，没有就写"干净无污损"）
      * ⭐ 布料物理状态（挺括/柔软垂坠/因潮湿贴身/因战斗撕裂/因风化褪色起毛）
    - 特征道具/标志：外观、材质、持握方式或佩戴位置
    - 体态气质：身材比例 + 身材体型(高挑/矮小/健壮/纤细/丰腴等) + 典型姿态 + 一个精确的气质方向词（如"妖媚危险"而非"高冷"）
    - 光影基调：与视频整体光影一致的角色打光

    常见错误（必须避免）：
    ❌ 唇色随意降级（subject_description 说 "red lips/深红唇" 但 prompt 写成"淡粉色"）
    ❌ 服装开合错误（subject_description 说"低胸/露肩/露背"但 prompt 写成"高领包裹至下颌"）
    ❌ 姿态角度错误（subject_description 说"侧目/低头"但 prompt 写成"正面直视镜头"）
    ❌ 气质方向偏移（画面是妖媚/诱惑/危险/癫狂，但 prompt 写成"冷峻威严/端庄优雅"）
    ❌ 遗漏头饰装饰品（很多角色最大的辨识度就在头饰/犄角/面纱，遗漏等于丢了一半特征）
    ❌ 编造不存在的细节（subject_description 没提到的东西不要自己加，不确定就不写）
    ❌ 服饰质感偏移（原视频中衣物是破旧/陈旧/沾血的，但 prompt 描述为崭新精美无瑕——或者反过来）
    ❌ 忽略污渍和磨损细节（subject_description 中描述了"破损""泥污""血迹"但 prompt 里没有体现）
    ❌ 美化倾向（将原视频中粗糙、朴素、残破的风格不自觉地美化为精致、华丽、干净的风格）
    ❌ 忽略身材体型描述（没有描述角色是高挑/矮小/健壮/纤细/丰腴等）

    角色完整性要求（极其重要）：
    - 每个 shot 的 character_refs 中引用的角色，都必须在 character_sheets 中有对应条目
    - 不能出现 shot 引用了 character_sheets 中不存在的角色 ID
    - 角色 ID 命名规则：主角用 char_A/B/C...，配角用描述性 ID 如 char_monk、char_snake_woman

    ═══════════════════════════════════════════
    二、单张场景参考图（scene_reference）—— 环境与比例锚点
    ═══════════════════════════════════════════

    全片生成一张主要场景参考图，画幅比与原视频一致。prompt 必须来自 timeline 的环境、光影、色调和空间关系。
    场景图可以带主角，用于明确人物与环境的比例；如带主角，必须引用 character_sheets 中的角色并保持一致。
    只生成一张独立、干净的场景图，不得生成九宫格、拼贴、多格分镜故事板、镜头运动曲线、表格或文字标注。
    scene_reference 输出 prompt、是否带主体、引用角色 ID 和简短使用说明，供最终视频 prompt 的「场景：@场景1」引用。

    ═══════════════════════════════════════════
    三、首帧图（first_frame_prompt）—— 关键镜头的视觉起点
    ═══════════════════════════════════════════

    以下镜头必须生成 first_frame_prompt：
    - narrative_function 为 hook 的镜头（开场第一印象）
    - narrative_function 为 payoff/twist 的镜头（视觉转折点）
    - 包含新场景/新环境首次出现的镜头
    - 包含复杂构图、多角色互动、大场景的镜头
    - attention_level >= 4 的镜头

    首帧图 prompt 必须包含：
    - ⭐ 画幅比：首帧图的画幅比必须与原视频一致（从 meta.aspect_ratio 获取，如 16:9/9:16/1:1），prompt 开头必须写明画幅比
    - 画面构图：景别 + 角色位置 + 视觉重心（如"Wide Shot 大全景，人物居画面下三分之一处，上方留大面积天空"）
    - 角色状态：引用 character_sheets 中的角色（如"角色A 面朝镜头，右手持剑，微侧身"），保留关键辨识特征
    - 环境细节：具体空间描述，材质、光影、氛围物件（不能用"某个环境"这种泛词）
    - 光影层次：主光源方向+补光+轮廓光+色温（如"顶部冷白主光从右侧45度打下，左侧暖色反射补光，边缘冷蓝轮廓光"）
    - 色调氛围：整体色调方案 + 后期风格（如"低饱和青橙对比调色，暗部偏蓝绿，高光偏暖橙"）
    - 风格锚定：与视频和角色图严格一致
    - 画质规格：保持原 frames 的手机成像——轻微失焦、动作软化、暗部细小随机噪点、手机降噪与平台压缩；禁止 8K/电影级/masterpiece
    - 末尾禁止项："禁止：任何文字、字幕、LOGO、水印"

    不需要首帧图的镜头（简单运镜延续、无场景切换）：first_frame_prompt 填空字符串。

    ═══════════════════════════════════════════
    四、分镜视频 prompt（shots）—— 即梦视频生成提示词
    ═══════════════════════════════════════════

    核心要求：
    1. 所有提示词必须使用中文
    2. 每个 shot 的 prompt 必须完整可用，统一采用「主体 / 场景 / 音乐 / Shot 编号」四段式
    3. hook、高潮和中段都优先写清楚实际视觉事件，不用空泛的史诗化、情绪化修饰堆高复杂度
    4. 运镜只保留必要且可执行的描述，可用中英混合短语（如"Slow Crane Up 缓慢升镜"）
    5. 每个 prompt 末尾加"禁止：任何文字、字幕、LOGO或水印"
    6. 最终 prompt 禁止时间戳；镜头数量决定节奏，超长内容再给拆分建议
    7. 默认生成 BGM 并叠加对应音效；只有用户明确要求不要 BGM 时才关闭。BGM 必须给出经近期抖音趋势核实的具体参考、类型、BPM、音色、情绪与卡点，禁止泛写
    8. 视频生成优先 720p；不要求 1080p/4K/8K，定稿后再外部放大

    提示词风格锚定要求（防止风格偏移）：
    将必要的风格锚定压缩成短语，放入场景行或第一个 Shot，不得放在「主体：」之前，也不得展开成长篇画质标签。
    根据 realism_level 选择一种准确锚定即可：真人实拍 / 超写实CG / 3D渲染 / 动画渲染 / 抽象实验。

    ⚠️ 风格判定优先级（当字段之间矛盾时，严格按此优先级）：
       realism_level > skin_texture > camera_equipment_feel > production_look
       即：realism_level 是最终裁决者。
       如果 realism_level = "photorealistic" 但 production_look 中出现了 "UE5"/"Unreal Engine"/"游戏引擎" 等词，
       必须忽略 production_look 中的游戏化描述，按 photorealistic 生成风格锚定前缀。
       绝不能因为 production_look 里碰巧提到了"UE5"就把写实视频的 prompt 写成3D游戏风格。

    风格交叉验证（防止一阶段误判传导）：
    - 在生成 prompt 前，请先对 analysis.json 中的各风格字段做交叉验证：
      * 如果 realism_level = "photorealistic" 且 skin_texture 描述了真实皮肤细节（毛孔、汗水、污垢），
        那么无论 production_look 写了什么，都必须使用"电影级真人实拍"风格锚定，
        绝不能使用"UE5渲染"、"3D渲染"、"CG"等词汇
      * 如果 realism_level = "3d-render" 但 skin_texture 描述像真人（"真实皮肤毛孔可见"），
        使用"超写实CG渲染"而非"UE5游戏引擎"
      * 如果 camera_equipment_feel 提到了真实摄影机型号（如 ARRI、RED、Sony），
        这是"真人实拍"的强信号，即使 production_look 说了别的，也应优先按写实处理
    - 风格锚定词选择禁忌：
      * 当 realism_level = "photorealistic" 时，绝对禁止使用以下词汇：
        "UE5"、"虚幻引擎"、"Unreal"、"游戏引擎"、"3D渲染"、"CG渲染"
      * 应该使用：
        "电影级真人实拍"、"cinematic live-action"、"自然皮肤质感"、"写实摄影风格"

    2. 主体描述要求：
       - 完整外貌、服装和体态写入 character_sheets，用于生成主体参考图
       - 最终视频 prompt 的「主体：」只引用对应 @主体/@图片并说明身份，不重复参考图已经表达的细节
       - 只有参考图无法表达的状态变化（如战损、换装）才在对应 Shot 补充

    3. 场景和光影要求：
       - 详细环境与光影用于生成一张独立场景参考图；场景图可带主体以锁定比例
       - 最终视频 prompt 的「场景：」只引用该场景图并补充真正需要变化的环境状态
       - 不生成、不上传拼接式分镜故事板

    4. 镜头要求：
       - 每个 Shot 写清景别/机位 + 动作事件 + 必要运镜 + 关键音效
       - 利用 timeline 的 camera_action 和 camera_details，但不堆砌焦距、器材和同义运镜词

    ═══════════════════════════════════════════
    五、输出格式
    ═══════════════════════════════════════════

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
        "shot_count": number,
        "character_count": number
      },
      "character_sheets": [
        {
          "id": "char_A",
          "name": "角色名或描述性标签（如'黑衣剑客'、'白发少女'）",
          "role": "主角/配角/背景角色",
          "appears_in_shots": [1, 2, 5],
          "prompt": "完整的角色参考图生成提示词（中文，必须包含构图指令+风格锚定+五官+发型+服装+体态+光影+画质规格+禁止项）",
          "visual_tags": ["关键视觉标签，用于后续 prompt 快速引用"]
        }
      ],
      "scene_reference": {
        "prompt": "一张独立场景参考图提示词，禁止故事板/拼贴/文字标注",
        "includes_subject_for_scale": true,
        "character_refs": ["char_A"],
        "usage_note": "上传为 @场景1，用于锁定环境和主体比例"
      },
      "shots": [
        {
          "index": 1,
          "time_range": "仅供分析和后期定位，不得写入 prompt",
          "duration_seconds": 4,
          "narrative_function": "hook",
          "attention_level": 5,
          "prompt": "完整 Seedance 提示词；普通多镜头用 Shot 编号，固定监控/一镜到底用单段连续动作流程，无时间戳",
          "first_frame_prompt": "完整的首帧图生成提示词（中文，包含构图+角色+环境+光影+色调+画质+禁止项），不需要则为空字符串",
          "first_frame_required": true,
          "character_refs": ["char_A"],
          "asset_hints": ["素材建议"],
          "original_segments": [{"start": 0, "end": 2}, {"start": 2, "end": 4}],
          "style_anchor": "写实真人/3D渲染/动画/etc",
          "subject_description_summary": "本镜头的人物外貌摘要"
        }
      ],
      "prompt_versions": [
        {
          "id": "A",
          "name": "原片代表造型",
          "character_prompt": "完整、独立、可直接粘贴的人物参考图提示词；保持原片画幅/场景/机位",
          "character_prompts": [
            {"label": "装扮一（生成 @图片1）", "prompt": "第一套完整人物参考图提示词"},
            {"label": "装扮二（上传 @图片1 后生成 @图片2）", "prompt": "明确引用 @图片1 锁定同一人，只改变第二套发型/妆容/服装/配饰的完整提示词"}
          ],
          "video_prompt": "完整、独立、可直接粘贴的视频提示词"
        },
        {
          "id": "B",
          "name": "人物造型变体 B",
          "character_prompt": "再次完整写全；只换发型/妆容/服装/配饰",
          "video_prompt": "再次完整写全；场景/画幅/机位保持原片"
        },
        {
          "id": "C",
          "name": "人物造型变体 C",
          "character_prompt": "再次完整写全；不得写同上或引用 A/B",
          "video_prompt": "再次完整写全；可直接生成"
        }
      ],
      "workflow_note": "生成顺序建议：1.生成主体参考图 → 2.生成一张场景参考图并确认比例 → 3.核对近期抖音热门 BGM 依据 → 4.以 720p 粘贴四段式 prompt 生成 → 5.按需后期替换配乐和放大"
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


def _extract_continuity_directives(analysis_data: dict) -> str:
    """
    从 analysis_data 中提取运镜、音画、场景连贯性信息，生成 prompt 注入段。
    这些指令会被注入到 user prompt 中，指导 LLM 在生成视频 prompt 时保持连贯性。
    """
    directives = []

    # 1. 运镜连贯性
    cam = analysis_data.get("camera_language", {})
    dominant = cam.get("dominant_movement", "")
    continuity = cam.get("movement_continuity", "")
    analysis_blob = json.dumps(analysis_data, ensure_ascii=False).lower()
    is_fixed_surveillance = any(
        kw in analysis_blob
        for kw in ("监控", "门铃", "猫眼", "门载", "cctv", "doorbell", "security camera")
    )
    if is_fixed_surveillance:
        directives.append(
            "⭐ 固定监控连续性：不得套用 Orbit、Dolly、Push In、Handheld 等通用贯穿运镜。"
            "摄像头只能保持固定，或被安装载体带动；必须从连续帧提取固定地标的屏幕移动方向，"
            "用地标流动锁定载体运动，禁止独立跟拍、推进和重新构图。"
        )
    elif dominant and any(kw in continuity for kw in ("不停", "连续", "全程")):
        directives.append(
            f"⭐ 运镜贯穿：原视频运镜为「{dominant}」且「{continuity}」，"
            f"prompt 必须简短声明贯穿运镜，并在相关 Shot 中延续运镜状态（如「Orbit持续旋转中」），"
            f"不能让相邻 Shot 看起来像互不相关的静态画面"
        )

    # 2. 音画协同
    avs = analysis_data.get("audio_visual_sync", {})
    music_genre = avs.get("music_genre", "")
    bgm_reference = avs.get("recommended_bgm_reference", "")
    bgm_style = avs.get("recommended_bgm_style", "")
    bpm = avs.get("recommended_bpm", "")
    sync_plan = avs.get("music_sync_plan", "")
    if any((music_genre, bgm_reference, bgm_style, bpm, sync_plan)):
        directives.append(
            "⭐ BGM 依据："
            f"源视频类型「{music_genre or '未识别'}」；"
            f"近期抖音参考「{bgm_reference or '未核实实时趋势'}」；"
            f"建议风格「{bgm_style or '需结合画面具体补全'}」；"
            f"BPM「{bpm or '需结合节奏补全'}」；"
            f"同步方案「{sync_plan or '需结合动作和切镜补全'}」。"
            "默认生成同类原创 BGM 并叠加动作/环境音效；若参考未核实，不得冒充实时热门。"
        )
    char_rhythm = avs.get("character_rhythm_sync", "")
    if char_rhythm and "无" not in char_rhythm:
        directives.append(
            f"⭐ 人物律动：源视频人物「{char_rhythm}」。将它落实为 Shot 中的动作强弱、鼓点和切镜节奏，避免人物静止"
        )
    env_music = avs.get("environment_music_elements", "")
    if env_music and "无" not in env_music:
        directives.append(
            f"⭐ 场景音乐道具：源视频画面中包含「{env_music}」，仅在它实际影响画面时简短写入场景或 Shot"
        )
    beat_impact = avs.get("beat_impact_on_visuals", "")
    if beat_impact and "无" not in beat_impact:
        directives.append(
            f"⭐ 视觉卡点：源视频「{beat_impact}」。让 BGM 的重拍、抽拍、停顿和恢复与动作、切镜或反转准确对应"
        )

    # 3. 场景连续性（从 timeline 统计）
    timeline = analysis_data.get("timeline", [])
    if timeline:
        scene_cont_count = sum(
            1 for t in timeline
            if "同场景" in t.get("scene_continuity", "")
        )
        if scene_cont_count > len(timeline) * 0.5:
            directives.append(
                "⭐ 场景固定：原视频超过半数镜头为同一场景延续，"
                "prompt 必须在开头声明固定背景（如「XX为固定背景贯穿全片」），"
                "每次换装/变化时强调「背景不变」，避免 AI 为每套造型生成不同场景"
            )

    # 4. 非硬切过渡方式
    non_hard_transitions = []
    for t in timeline:
        tt = t.get("transition_type", "")
        td = t.get("transition_detail", "")
        if tt and "硬切" not in tt and "Hard Cut" not in tt and "无" not in tt and "直接" not in td:
            non_hard_transitions.append((t.get("start", "?"), tt, td))
    if non_hard_transitions:
        for start, ttype, tdetail in non_hard_transitions:
            directives.append(
                f"⭐ {start}秒处过渡方式为「{ttype}」：{tdetail}。"
                f"prompt 必须忠实描述此过渡效果（方向/媒介/持续时间），不能简化为硬切"
            )

    if not directives:
        return ""
    return (
        "████████ 从一阶段分析自动提取的连贯性指令 ████████\n"
        + "\n".join(directives)
        + "\n████████████████████████████████████████████████████████████████████\n"
    )


def _resolve_style_directive(analysis_data: dict, style_hint: str | None = None, image_model: str = "nanobanana") -> str:
    """
    根据 analysis.json 中的 realism_level 和用户提供的 style_hint
    硬编码生成风格指令。这条指令会被直接注入 user prompt。
    """
    vl = analysis_data.get("visual_language", {})
    realism = vl.get("realism_level", "").lower()
    skin = vl.get("skin_texture", "")
    global_style = vl.get("global_style_direction", "")

    parts = []

    # 全局风格定调（如果一阶段提供了）
    if global_style:
        parts.append(dedent(f"""\
        ████████ 全局风格定调（整部片子的视觉基调，统领一切）████████
        {global_style}

        所有角色图、首帧图、分镜 prompt 必须严格服从此基调。
        任何单个镜头的风格描述都不能脱离此基调。
        角色的服饰质感（崭新/陈旧/破损/战损）、环境氛围（明亮/阴暗/荒芜/繁华）、
        色调倾向（冷暗/暖亮/高对比/低饱和）都必须与此基调一致。
        ████████████████████████████████████████████████████████████████████
        """))

    # 用户自定义风格描述（最高优先级）
    if style_hint:
        parts.append(dedent(f"""\
        ████████ 用户风格指示（最高优先级，必须严格遵守）████████
        用户对视频风格的描述："{style_hint}"

        所有生成的 prompt（角色图、首帧图、分镜 prompt）必须严格匹配用户描述的风格。
        用户的风格描述覆盖 analysis.json 中所有风格相关字段（realism_level、production_look 等）。
        如果用户描述了人种/五官特征（如"中式五官""东方面孔"），角色设定图中必须体现。
        ████████████████████████████████████████████████████████████████████
        """))

    # 基于 realism_level 的自动风格指令
    if realism in ("photorealistic", "semi-realistic"):
        # 判断是否为手机/UGC 向内容——决定用"手机真实质感"还是"电影级"
        meta = analysis_data.get("meta", {})
        primary_format = str(meta.get("primary_format", "")).lower()
        equip = vl.get("camera_equipment_feel", "")
        prod = vl.get("production_look", "")
        cam_signal = f"{equip} {prod}"
        is_ugc_like = (
            "ugc" in primary_format
            or any(kw in cam_signal for kw in ("手机", "自拍", "POV", "pov", "前置", "vlog", "手持"))
        )

        if is_ugc_like:
            parts.append(dedent("""\
            ████████ 强制风格指令（最高优先级，覆盖一切其他风格描述）████████
            本视频的 realism_level = "photorealistic"（真人写实），且为手机拍摄的 UGC/网红向短视频。
            核心要求是「经过抖音美颜和平台压缩的真实手机 Vlog 暂停帧」，不是影棚高清照片，也不是故意做旧的脏图。

            - 人物参考图必须保持原视频画幅、场景、时段和机位；开头直接写手机型号感/前后置/焦段/拍摄距离，不写角色设定图
            - 视频 prompt 第一个 Shot 可写"真人实拍，普通手机拍摄"，不写电影级、广告片级
            - A/B/C 只更换人物发型、妆容、服装与配饰；每版人物图和视频 Prompt 独立写全

            人物参考图和视频都必须写入“手机物理缺陷硬约束”，不能只泛写“轻微噪点/轻微模糊”：中间调与暗部有普通观看尺寸下明确可见的细小随机亮度颗粒；少量彩噪在视频中随曝光逐帧变化；发丝、手指、耳环、衣角等一旦运动就产生与运动方向一致的动态拖影；另有轻微焦点不实、偶发对焦呼吸、滚动快门轻微形变、手持随机微抖、自动曝光/白平衡小幅泵动、高光轻微溢出、手机降噪局部涂抹、短视频压缩块与色阶断层。人物静止时五官与衣料仍可辨认，但不能处处锐利、完全无噪点。

            美颜可以明显：肤色提亮、腮红、轻微大眼瘦脸和柔焦；但保留眼下、鼻翼、嘴角、发际线、颈部和关节的真实明暗。肤色、人种与地域特征以 frames 证据和用户指示为准，不得机械统一成东亚冷白皮。

            ⭐ 现实空间逻辑：交通舱内的飞机行李舱位于座位排上方顶棚边缘，沿车厢/机舱纵向、平行过道延伸；高铁开放式行李架同理位于窗侧座位排上方。人物拿放物品时，双手应接触窗侧上方行李舱/架的下沿或把手；严禁把行李舱/架生成在过道中央、横跨过道或悬浮在人物头顶。后天泳衣晒痕必须由细带形成：正面轻微可见、向侧腰迅速羽化消失，禁止粗线、完整 V、白线或贴图感。

            绝对禁止：UE5/虚幻引擎/3D/CG、电影级、广告片质感、超清锐利、影棚完美打光、HDR、4K/8K 超清精修、完全无噪点、无颗粒、全程锐利、稳定器般平滑、塑料皮；也禁止满屏粗噪点、固定噪点纹理、压低清晰度做旧、整幅朦胧、脏污水渍感或糊成一团。

            应使用：真人手机 Vlog、可见细颗粒、逐帧变化彩噪、方向性动作拖影、对焦呼吸、滚动快门、手持随机微抖、曝光/白平衡泵动、高光轻微溢出、手机降噪、平台二次压缩、现场环境光、美颜但保留真实结构
            ████████████████████████████████████████████████████████████████████
            """))
        else:
            parts.append(dedent("""\
            ████████ 强制风格指令（最高优先级，覆盖一切其他风格描述）████████
            本视频的 realism_level = "photorealistic"（真人写实）。
            所有生成的 prompt（角色图、首帧图、分镜 prompt）必须使用以下风格锚定：
            - 角色图开头必须写："写实人像摄影风格角色设定图" 或 "电影级真人写实角色设定图"
            - 分镜 prompt 的第一个 Shot 可简写"电影级真人实拍"或"cinematic live-action"，不得放在"主体："之前
            - 首帧图开头必须写："电影级写实摄影构图" 或 "cinematic photography"

            绝对禁止使用以下词汇（出现即为错误）：
            "UE5"、"虚幻引擎"、"Unreal Engine"、"游戏引擎"、"3D渲染"、"CG渲染"、
            "超写实CG"、"高端CG"、"次表面散射"、"3D角色设定"、"CG角色设定"

            应该使用的词汇：
            "真人实拍"、"自然皮肤质感"、"真实毛孔细节"、"电影级摄影"、"自然光影"、
            "写实人像"、"cinematic"、"photorealistic"、"natural skin texture"
            ████████████████████████████████████████████████████████████████████
            """))
    elif realism == "3d-render":
        is_hyper_real = any(kw in skin.lower() for kw in ("pore", "毛孔", "sweat", "汗", "realistic"))
        if is_hyper_real:
            parts.append(dedent("""\
            ████████ 强制风格指令 ████████
            本视频的 realism_level = "3d-render"，且皮肤质感极其写实。
            所有 prompt 使用"超写实CG渲染"风格锚定，而非"UE5游戏引擎"。
            角色图开头写："超写实CG角色设定图，毛孔级皮肤细节"
            禁止使用"UE5"、"游戏引擎"等明显游戏化词汇。
            ████████████████████████████████
            """))
        else:
            parts.append(dedent("""\
            ████████ 强制风格指令 ████████
            本视频的 realism_level = "3d-render"，为 3D 渲染/游戏风格。
            所有 prompt 使用"UE5超写实3D渲染"或类似3D风格锚定。
            ████████████████████████████████
            """))
    elif realism == "anime":
        parts.append(dedent("""\
        ████████ 强制风格指令 ████████
        本视频的 realism_level = "anime"，为动画/国漫风格。
        所有 prompt 使用对应的动画渲染风格锚定。
        禁止使用"真人实拍"、"UE5"等词汇。
        ████████████████████████████████
        """))

    # 图片生成平台规范
    if image_model == "nanobanana":
        parts.append(dedent("""\
        ████████ 图片生成平台：NanoBanana（Google）████████
        角色参考图和首帧图的 prompt 是给 NanoBanana 图片生成模型使用的，必须遵守：
        1. 所有提示词必须使用中文
        2. prompt 风格要求：直接描述画面内容，不需要加 Midjourney/SD 风格的参数标签
           ❌ 错误："--ar 3:4 --v 6 --style raw"（这是 Midjourney 语法）
           ❌ 错误："masterpiece, best quality, 1girl"（这是 SD/NovelAI 语法）
           ✅ 正确：直接用自然语言描述画面，如"角色设定图，正面全身，纯黑背景，..."
        3. 人物人种/地域特征必须以 frames 证据和用户明确指示为准，不得因题材机械假设为东亚或欧美面孔
        4. 人物图 prompt 需写清可观察的五官、肤色和后天日晒特征；不确定时使用中性客观描述
        5. 画面描述顺序建议：原画幅/原场景/真实机位 → 人物外貌 → 姿态/表情 → 服装/道具 → 环境光 → 手机 Vlog 画质 → 禁止项
        6. 不要堆砌 8K/masterpiece/best quality；用中文写清轻微失焦、动作软化、暗部细噪点、手机降噪和平台压缩
        ████████████████████████████████████████████████████████████████████
        """))
    else:
        parts.append(dedent("""\
        ████████ 图片生成平台：即梦（Seedance）图片生成 ████████
        角色参考图的 prompt 是给即梦（Seedance）平台的图片生成功能使用的，必须遵守：
        1. 所有提示词必须使用中文
        2. 人物面部、肤色和地域特征必须以 frames 证据与用户指示为准，不机械统一人种
        3. 人物参考图保持原片画幅、场景、时段和机位；B/C 默认只更换发型、妆容、服装与配饰
        4. 使用"手机 Vlog 人物参考图/视频暂停帧"等自然描述，不写角色设定图或概念设计
        5. 画质写轻微失焦、动作软化、暗部细小随机噪点、手机降噪和平台压缩；禁止 8K/超精细/character design sheet
        ████████████████████████████████████████████████████████████████████
        """))

    return "\n".join(parts)


def _resolve_realism_camera_directive(analysis_data: dict, style_hint: str | None = None) -> str:
    """
    针对「真人写实短视频」注入「真实质感 + 动态运镜」指令。

    解决两个高频翻车点（一阶段分析往往捕捉不到、二阶段又容易做反）：
      1. 机位定死：人在动、背景钉死不动 → 人物与背景割裂、一眼假
      2. 画面太干净：缺手机拍摄的噪点/朦胧/动态模糊/自然抖动 → "AI 味"重

    核心理念：analysis_data 里的运镜（固定机位）和画质（电影级/高清/稳定器）描述
    仅供参考，对手机 UGC/网红向短视频要主动纠偏，不能照搬。
    """
    vl = analysis_data.get("visual_language", {})
    realism = str(vl.get("realism_level", "")).lower()
    analysis_blob = json.dumps(analysis_data, ensure_ascii=False).lower()
    is_rigged_surveillance = any(
        kw in analysis_blob
        for kw in (
            "监控", "摄像头", "门铃", "门载", "doorbell", "security camera",
            "cctv", "车载固定", "头盔相机", "bodycam",
        )
    )
    is_door_mounted = any(
        kw in analysis_blob
        for kw in ("门铃", "门载", "门扇", "门板", "猫眼", "doorbell", "door-mounted")
    )
    has_handheld_prop = any(
        kw in analysis_blob
        for kw in ("快递", "纸箱", "信封", "纸袋", "包裹", "钥匙", "手机", "parcel", "package")
    )

    # 真人写实类或刚性安装监控类生效；监控物理规则不依赖 realism 字段是否完整
    if realism not in ("photorealistic", "semi-realistic") and not is_rigged_surveillance:
        return ""

    meta = analysis_data.get("meta", {})
    primary_format = str(meta.get("primary_format", "")).lower()
    avs = analysis_data.get("audio_visual_sync", {})
    char_rhythm = str(avs.get("character_rhythm_sync", ""))
    cam = analysis_data.get("camera_language", {})
    dominant = str(cam.get("dominant_movement", ""))
    equip = str(vl.get("camera_equipment_feel", ""))
    prod = str(vl.get("production_look", ""))

    cam_signal = f"{dominant} {equip} {prod}"

    # 拍摄方式判断（决定运镜的物理逻辑——这是最容易翻车的地方）
    is_selfie_signal = any(kw in cam_signal for kw in ("自拍", "POV", "pov", "前置", "vlog", "selfie"))
    is_handheld = any(kw in cam_signal for kw in ("手持", "handheld"))
    is_fixed = is_rigged_surveillance or any(
        kw in dominant for kw in ("固定", "static", "Static", "三脚架", "tripod", "架设")
    )
    is_dance = bool(char_rhythm) and "无" not in char_rhythm and any(
        kw in char_rhythm for kw in ("律动", "舞", "bounce", "卡点", "拍点", "摇摆", "弹跳", "节奏")
    )
    is_tracking = any(kw in dominant for kw in ("track", "Track", "跟", "环绕", "orbit", "Orbit", "移"))

    lines = [
        "████████ 真实质感与运镜物理逻辑指令（最高优先级，覆盖 analysis 中的运镜/画质判断）████████",
        "",
        "⚠️ 重要纠偏：analysis_data 中的运镜（如「固定机位」「Dolly/Tracking」）和画质（如「电影级」",
        "「高清」「稳定器」）描述仅供参考，不要照搬。手机 UGC/网红向短视频的运镜必须符合真实拍摄的",
        "物理逻辑，否则会一眼假。请严格按下面判定出的「拍摄方式」来组织运镜：",
        "",
        "【一、运镜物理逻辑（按本片的实际拍摄方式，严格遵守）】",
    ]

    # 模式优先级：刚性安装监控 > 固定机位互动 > 手持自拍贴脸 > 手持跟拍 > 默认手持
    if is_rigged_surveillance:
        lines += [
            "- ⭐ 本片为刚性安装的监控/门铃/车载类固定机位：摄像头相对安装载体的位置、朝向、高度、俯仰角和焦距全程不变。",
            "- ⭐ 全片必须是一条未经剪辑的连续录像：不用 Shot 编号，不切镜、不转场、不跳时、不重置构图，不出现第二台摄像机或第三人称机位。",
            "- ⭐ 载体静止时画面绝对固定；载体运动时摄像头只能随载体做同一个刚体运动，禁止独立摇移、推拉、横移、升降、变焦、跟拍、自动追踪或重新构图。",
            "- ⭐ 人物把摄像头当作无人关注的安防设备，不看镜头、不对镜头互动；人物离开固定视野后，摄像头不得追随。",
            "- ⭐ 最终 prompt 用单段「连续动作流程：」按先后顺序描述完整事件，禁止拆成 Shot 01/02/03。",
        ]
        if is_door_mounted:
            lines += [
                "- ⭐ 门载猫眼机位：自家门明确向屋内开启；摄像头只被同一门板带动，围绕固定合页做一次有限、连续的被动转动。视野必须从正对邻居门，逐渐扫过自家门框内侧，最终转到部分自家玄关。",
                "- ⭐ 该变化不是镜头独立向前推进、横移或跟随人物，也不能转向楼道另一侧。门停止后摄像头立即固定在门板当前角度，绝不能切成门外第三个人向屋内拍。",
                "- ⭐ 门载空间锁定：自家入口就在摄像头旁边的画面近端盲区，自家门本身不可见；画面中可见的正对面门是远端邻居门，只能保持关闭、作为静止背景。",
                "- ⭐ 人物回家必须走向摄像头，在画面中逐渐变大，然后从画面下缘/侧缘进入近端自家入口；绝不能继续向画面深处走、靠近或进入可见的邻居门。",
            ]
        if has_handheld_prop:
            lines += [
                "- ⭐ 持物连续性：纸箱、信封、纸袋、手机、钥匙等每一刻都必须由手、手臂、身体、地面或家具真实支撑，禁止悬空、漂浮、瞬移或无支撑换手。",
                "- ⭐ 拿快递后取钥匙必须写清腾手过程：单箱可先转移到左前臂并夹紧身体，再用右手拿钥匙；多件重物应先平稳放地、双手开锁、再重新抱起。必须明确哪只手承托、哪只手开锁。",
            ]
    elif is_fixed and not is_tracking:
        lines += [
            "- ⭐ 本片为「固定机位」拍摄：手机/相机架设在固定位置（桌面支架/三脚架），机位本身不移动，",
            "  只有轻微的自然晃动（桌面震动级别的微抖），绝不是手持移动，也不做镜头推拉。",
            "- ⭐ 景别变化完全靠人物自身前后移动实现，且要有自然的节奏变化（不要全程固定在同一距离）：",
            "  人物时而主动靠近镜头做可爱表情/脸部特写、时而退后到能拍到全身时做身体动作/展示穿搭，",
            "  一近一远自然交替推进，而不是靠镜头 Push In / Pull Out。镜头位置始终不动。",
            "- ⭐ 焦点随人物与镜头的远近自然呼吸变化；当人物的手、道具靠近遮挡镜头时，焦点转移使",
            "  背景和身体短暂虚化，移开后重新合焦——这种「焦点呼吸 / 失焦再合焦」是真实感的关键。",
            "- ⭐ 人物与镜头有直接互动：看镜头、对镜头做手势、伸手靠近或短暂遮挡镜头、凑近做表情等。",
        ]
    elif is_selfie_signal or (is_handheld and not is_tracking):
        lines += [
            "- ⭐ 本片为「单手持手机自拍」：人物一只手臂伸出持手机对着自己拍，镜头始终在一臂距离，",
            "  紧贴聚焦人物的脸和上半身，景别恒定为近景 / 中近景。",
            "- ⭐⭐ 人物朝向铁律（最容易出逻辑硬伤，务必遵守）：自拍时手机始终举在人物正前方，",
            "  所以人物的脸和正面【全程朝向镜头】。绝不可能出现「侧身对镜头」「背对镜头」",
            "  「转身离开镜头」「身体侧向一旁」这类动作——这在自拍物理上不成立。",
            "  ⚠️ analysis 里若有「侧身 / 背对 / 转身 / 扭转上半身」等描述，那是第三人称跟拍视角的误读，",
            "  必须改写为正对镜头的等价动作，绝不能照搬。",
            "  人物能做的只有：正对镜头的表情变化、对镜头笑/说话、头部小幅左右摆动、",
            "  撩发、比手势、向前走动——脸始终冲着镜头。",
            "- ⭐ 关键物理约束：镜头绝不能拉远、推远、升降或绕到人物背后（禁止 Dolly Back / Pull Out /",
            "  Push Up / 大全景 / 环绕到背后 等任何运镜）。镜头与人脸距离恒定（一臂自拍距离）。",
            "- ⭐ 若人物原地转圈：是人举着手机一起转、手机始终在脸前（脸仍对镜头），背景在身后旋转流动，",
            "  【不是】人背对镜头、也不是镜头绕到其背后。",
            "- ⭐ 只有自然的单手自拍手抖（轻微、随机、有呼吸感），没有稳定器般顺滑运镜，",
            "  也没有刻意的电影感镜头调度（不要 Low-angle、不要 Crane、不要 Spin 环绕大调度）。",
        ]
    elif is_tracking:
        lines += [
            "- ⭐ 本片为手持跟拍：镜头手持跟随人物移动，紧跟主体并保持中近景聚焦主体，",
            "  与主体的距离相对稳定（不要忽远忽近的专业调度），叠加自然的手持呼吸感微抖，",
            "  避免稳定器般的绝对顺滑（那会显得像广告片而非真实记录）。",
            "- ⭐ 默认从主体的正面或斜前方拍摄，能看到主体的正脸/四分之三正面，",
            "  避免长时间从正后方/后侧跟拍主体背影（除非内容明确要拍背影）。",
        ]
    else:
        lines += [
            "- 按「手持拍摄」处理：全程自然手持微晃和呼吸感抖动，聚焦主体，与主体距离相对稳定，",
            "  避免专业运镜调度，也不要钉死成绝对静止机位。",
        ]

    if is_dance and not is_fixed:
        lines += [
            "- 人物随节拍律动：镜头可随律动做厘米级的轻微浮动同频呼吸，但幅度要小、自然，不喧宾夺主。",
        ]

    lines += [
        "",
        "【二、手机真实质感·抖音美颜与平台压缩画质（解决 AI 超清和满屏脏噪点两个极端）】",
        "真实抖音网红视频不是影棚高清精修，也不是故意做旧；要像普通手机拍摄、经过美颜和平台二次压缩的 Vlog。逐条体现：",
        (
            "- ① 设备与拍法：固定安防摄像头/门铃摄像头真实质感；载体静止时画面不手抖，载体运动时只随载体做刚体运动；禁止手持感、稳定器感和专业运镜；"
            if is_rigged_surveillance else
            "- ① 设备与拍法：智能手机(iPhone/安卓)拍 + 抖音/美颜默认滤镜的柔光提亮氛围感；手持自然轻微晃动、偶有对焦拉风箱；不是相机/稳定器/专业摄影；"
        ),
        "- ② 观感：美颜滤镜可以好看，但不能干净到像 AI 人像；普通观看尺寸下也必须明确看得见细颗粒、轻微失焦、动作拖影和平台压缩，不能像高清照片；",
        "- ②b 噪点：白天阴影与中间调也保留可见但细小的随机亮度颗粒；夜景暗部同时保留细小亮度噪点与少量彩噪。视频噪点强度和分布随曝光逐帧轻微变化，不能被降噪抹净，也不能做成固定颗粒贴图或满屏粗噪点；",
        "- ③ 模糊来源：人物动作、手持微抖、焦点偏离、滚动快门和手机降噪都会产生动态软化；发丝、手指、饰品、衣角等一旦运动，必须出现与运动方向一致的真实拖影；静止五官仍可辨认但不处处锐利。保留偶发对焦呼吸和滚动快门轻微形变，禁止整幅朦胧发雾或糊成水渍；",
        "- ④ 宽容度与曝光：手机动态范围有限——高光略溢、自动曝光/白平衡随移动轻微漂移、偏暖或偏绿(轻微即可，别过曝死白/暗部死黑)；",
        "- ⑤ 皮肤：柔美但保留一点自然真实质感(细纹/毛孔隐约可见)，别磨皮到塑料假面、也别锐化出颗粒；",
        "- ⑥ 光线与取景：现场自然光/暖光氛围，非影棚布光；取景随意自然。",
        "⛔ 画质禁用（两个极端都禁）：① 太假——4K/高清/超清/锐利凌厉/HDR完美/电影级/稳定器/影棚完美打光/CG/塑料完美皮肤/无噪点/无颗粒/全程锐利；② 太脏——满屏噪点/暗部粗颗粒/压低清晰度做旧/固定颗粒贴图/朦胧发糊/压缩脏块/脏污水渍感/糊成一团。",
        "✅ 正向强约束：画面像经过美颜与平台压缩的真实手机 Vlog——中间调和暗部可见细小随机颗粒，彩噪随曝光逐帧变化，动作产生方向性拖影，并保留对焦呼吸、滚动快门、手持随机微抖、曝光/白平衡泵动、高光溢出、降噪涂抹与压缩块；五官可辨但不处处锐利。",
        "⭐ 核心口诀：美颜好看不能覆盖手机物理缺陷；若只能二选一，优先保留噪点、动态模糊和曝光瑕疵，而不是干净精修。",
        "- 画质松紧：偏清晰时不能只加一句“轻微噪点”，必须把可见细颗粒、逐帧彩噪、方向性拖影、对焦呼吸、滚动快门、曝光泵动和压缩块写进最终 prompt；不要给整幅铺模糊或固定颗粒。",

        "",
        (
            "【三、人物动作自然度 + 单机位连续性（刚性安装监控）】"
            if is_rigged_surveillance else
            "【三、人物动作自然度 + 多镜头切换（解决神情动作僵硬、镜头单调切换假）】"
        ),
        "- 动作要松弛自然，有真实的重心转移、惯性、细微停顿和呼吸感，",
        "  表情自然不摆拍、不僵硬，避免逐拍机械摆动的「机器人/提线木偶感」。",
        "- 动作之间要有自然过渡和衔接，而不是一个个孤立的定格姿势。",
        *(
            [
                "- ⭐ 监控内容必须保持一个连续机位：全程不切镜、不转场、不跳时、不改变景别，也不为了丰富画面加入第三人称视角。",
                "- ⭐ 人物只能在固定画幅内进入和离开；离开画面后不追拍。画面变化来自人物、环境或安装载体本身，不来自摄像头独立运动。",
            ]
            if is_rigged_surveillance else
            [
                "- ⭐ 多镜头自然切换（展示/穿搭/vlog 类）：单一机位从头摆拍到尾会僵硬、无聊、切换假；先看 frames 有几种镜头动作，",
                "  15 秒内自然快切 3-4 个不同镜头（手持前置自拍近景 ↔ 第三人称全身 ↔ 蹲/坐近景 ↔ 背身回眸等），自拍与第三人称混用、",
                "  景别角度都换一换，镜头间用干脆的自然硬切（非缓慢转场）；每个镜头内动作符合真实人体力学，绝不一格一格摆姿势。",
            ]
        ),
        "",
        "【四、实时速度·严禁升格慢放（极易翻车点，务必重视）】",
        "- ⚠️ 先分清两件事：问题往往不是「动作做得慢」，而是整个视频的【播放节奏】被 AI 处理成了",
        "  0.7-0.8 倍速的升格慢放 / 高帧率慢镜头效果——即梦对夜景、情侣、唯美场景尤其爱这么做，必须消除。",
        "- ✅ 必须声明：全程 real-time 实时速度、1 倍速正常播放节奏、画面时间流速等于现实时间，",
        "  动作以正常生活速率推进（正常走路看起来就该是正常走路的速度，不快不慢）。",
        "- ⛔ 严禁：升格 / 高帧率慢放 / slow motion / 慢镜头 / 子弹时间 / 时间拉伸 / 电影感放慢节奏 / 变速。",
        "- ⛔ 同时禁用会诱导抒情慢镜头的词：浪漫唯美 / 轻盈飘逸 / 优雅 / 漫步 / 缓缓 / 梦幻 / 唯美 /",
        "  flowing / dreamy / cinematic slow——这些词会让模型自动放慢节奏，一律不要用。",
        "",
        "【五、BGM + 音效（默认启用，用户明确关闭时例外）】",
        "- 默认生成与画面匹配的 BGM，并叠加脚步、衣料摩擦、风声、碰撞、机械、环境声等音效；只有用户明确说不要 BGM 时才关闭。",
        "- BGM 必须参考近期抖音热门视频的实际用法，写明具体参考曲目/热梗音乐、类型、BPM、核心音色、情绪和卡点；不得泛写‘流行音乐/电子乐’。",
        "- 优先生成同类原创 BGM，不复刻参考曲的歌词或完整旋律；近期趋势未核实时必须如实说明，不得伪造热度。",
        "",
        "【六、背景环境微动效·去假感（静止背景=一眼假，务必加）】",
        "- 静止僵死的背景是「一眼假」的重要来源，视频 prompt 必须给背景加自然的环境微动效，让画面「活」起来：",
        "  如吊扇/风扇缓缓转动、窗帘/发丝/衣角被风轻拂、灯串或屏幕暖光轻微明暗浮动、窗外光影或树影晃动、",
        "  蒸汽/水汽/尘埃在光里飘、远处有人或车虚焦走动、宠物/绿植细微晃动等。",
        "- 挑 1-2 个与场景匹配的微动效写进 prompt（别堆太多），核心是画面里始终有一点点在动的东西，避免死板定格感。",
        (
            "- ⚠️ 监控开场允许机位绝对静止；用声控灯、远处脚步或人物进入画面制造动态，绝不能添加手持晃动或镜头漂移。"
            if is_rigged_surveillance else
            "- ⚠️ 开头几秒尤其别完全静止：即使是「先起音乐/氛围铺垫、人物还没进入主动作」的开场，也要靠背景微动效(灯闪/暖光呼吸/镜头轻微手持晃)+人物细微预备动作(调整姿势/试音/拨头发/呼吸起伏)垫住，绝不能整个画面定格发死。"
        ),
        "",
        "【七、参考图=人物一致性锚点，不是视频首帧（I2V 关键）】",
        "- 喂给图生视频(I2V)的人物图只用于锁定人物形象一致性(五官/发型/身材/穿着)，不是要把这张图当静止首帧去「让它动起来」；",
        "- prompt 要说明「用同一个人物重新拍摄一段动态镜头，人物从第 0 秒就在自然动作」；",
        "- ⚠️ 别把参考图上为增强真实感而带的噪点/柔焦当成画面内容原样搬进视频(否则会出现「噪点/糊被当成动态内容、镜头一晃像水渍」的怪异感)——画质应由视频自己按上面「美颜滤镜柔和通透」重新生成。",
        "",
        "【八、无台词 + 场景物理合理性（易忽略的真实感细节）】",
        "- 无台词默认：动作/展示/律动类默认「不说话、无台词、无口型」(除非原片本就是口播)；默认 BGM 不等于生成人声台词，并保留动作与环境音效——AI 说话口型往往很假；",
        "- 场景物理合理性：prompt 里的场景元素/机位要符合现实——如地铁站不会有镜子(别写/别暗示「照镜子自拍」，手机自拍写明「手持前置摄像头自拍」)；作为背景的屏幕/电视应全程稳定显示内容(别黑屏、别从黑变有或有变黑、别忽明忽暗跳变)；生成前自查「这个元素/机位真实场景里会有吗」。",
    ]

    if style_hint:
        lines += [
            "",
            "（注：若本指令与上方「用户风格指示」冲突，以用户风格指示为准。）",
        ]

    lines.append("████████████████████████████████████████████████████████████████████")
    return "\n".join(lines)


def _resolve_platform_safety_directive(analysis_data: dict) -> str:
    """
    平台内容审查·安全措辞指令（即梦/抖音对女性主体、身材展示类内容有审查）。

    检测到女性主体时自动注入：避开身体敏感词，改用客观服装款式描述 + 得体气质护栏。
    经验来源：seedance-prompt-skill 的「版权审查 SOP」+「身材曲线安全措辞」。
    """
    blob_parts = []
    vl = analysis_data.get("visual_language", {})
    sdt = vl.get("subject_design_traits", "")
    if isinstance(sdt, list):
        blob_parts.extend(str(x) for x in sdt)
    else:
        blob_parts.append(str(sdt))
    for c in analysis_data.get("characters_detected", []):
        blob_parts.append(str(c.get("brief_description", "")))
        feats = c.get("distinguishing_features", [])
        if isinstance(feats, list):
            blob_parts.extend(str(x) for x in feats)
    summary = analysis_data.get("summary", {})
    blob_parts.append(str(summary.get("one_sentence", "")))
    for t in analysis_data.get("timeline", [])[:3]:
        blob_parts.append(str(t.get("subject_description", "")))
    blob = " ".join(blob_parts)
    analysis_blob = json.dumps(analysis_data, ensure_ascii=False).lower()
    is_surveillance = any(
        kw in analysis_blob
        for kw in ("监控", "摄像头", "门铃", "门载", "doorbell", "security camera", "cctv")
    )

    is_female = any(kw in blob for kw in ("女性", "女子", "女孩", "女生", "少女", "女人", "美女"))
    if not is_female:
        return ""

    return "\n".join([
        "████████ 平台审查·得体魅力措辞指令（女性主体；既要过审，又不能丢掉吸引力）████████",
        "核心理念：这类视频的吸引力恰恰来自「恰到好处的身材氛围感与魅力」，绝不能为了过审就",
        "阉割成平淡的「清爽健康」——那样会显得寡淡又 AI。正确做法是：保留高级的吸引力，",
        "只把「露骨/低俗」换成「得体、有质感、恰到好处」的表达。",
        "",
        "✅ 应当保留并强化（让人物有魅力、有氛围感）：",
        "- 修身/贴身/合体的剪裁，自然衬托出姣好的身形与身材比例（用「修身剪裁衬托身形」「身姿挺拔」",
        "  「曲线感」「身材比例好」「氛围感」「高级感」「恰到好处的吸引力」「微微的小性感」等得体措辞）；",
        (
            "- 自然、有生活感的眼神，视线落在行进方向、手中物品或正在进行的动作上；监控场景禁止看镜头或与镜头互动；"
            if is_surveillance else
            "- 自信、有魅力、有故事感的眼神，与镜头的眼神交流/对视（这是吸引力的关键，务必强调）；"
        ),
        "- 精致的发型、妆容、神态细节，整体气质迷人、有记忆点。",
        "",
        "⛔ 只规避真正会触发审查的「露骨/低俗」表达（把它们换成上面的得体说法，而非删掉魅力）：",
        "- 露骨身体词与性暗示：露点 / 裸露 / 情色 / 色情 / 低俗 / 挑逗 / 下流 / 淫 / 乳 / 事业线 /",
        "  深沟 / 紧绷凸显 / 衣不蔽体 等一律不要；",
        "- 镜头语言上：不要让镜头「怼向/特写/聚焦」胸、臀、裆等敏感部位（可以整体展示身姿，但不做部位特写）；",
        "- 服装描述用「款式+颜色+材质+修身剪裁」，可点出「衬托身形/曲线感」，但不写「露出某部位」的露骨描述。",
        "- 音频默认包含匹配画面的 BGM、动作音效和环境音效；涉及歌词时避免露骨、歧视或危险内容。用户明确不要 BGM 时才关闭。",
        "",
        "一句话拿捏分寸：要的是「高级的、恰到好处的吸引力与氛围感」，不是「露骨裸露」，也不是「平淡无魅力」。",
        "████████████████████████████████████████████████████████████████████",
    ])


def _extract_global_context(analysis_data: dict) -> dict:
    """提取全局风格上下文（不含 timeline），用于每批调用。"""
    return {
        k: v for k, v in analysis_data.items()
        if k != "timeline"
    }


def _resolve_music_generation_directive(
    analysis_data: dict,
    music_mode: str = "auto",
) -> str:
    """解析 BGM 开关；默认启用，仅显式 off 时只生成音效。"""
    if music_mode not in {"auto", "on", "off"}:
        raise ValueError("music_mode 必须是 auto、on 或 off")

    configured_mode = str(
        analysis_data.get("generation_preferences", {}).get("music_mode", "on")
    ).lower()
    resolved_mode = configured_mode if music_mode == "auto" else music_mode
    if resolved_mode in {"off", "none", "no", "false", "音效-only", "只要音效"}:
        return dedent("""\
        ████████ 用户明确要求关闭 BGM（覆盖默认规则）████████
        最终提示词的音乐行必须原样写：音乐：不要生成任何背景音乐，只生成对应的音效。
        不得再推荐、描述或生成任何 BGM，只保留画面对应的动作和环境音效。
        ████████████████████████████████████████████████████████████████
        """)

    return dedent("""\
    ████████ BGM 默认开启 ████████
    除非用户明确要求不要 BGM，否则最终提示词必须生成背景音乐并叠加对应音效。
    BGM 必须参考近期抖音站内热门视频/热歌的实际用法，给出具体参考曲目或热梗音乐、音乐类型、BPM、核心乐器/音色、情绪和动作/叙事节奏卡点；一镜到底内容不得为卡点而切镜。
    优先生成同类原创 BGM，不照搬原曲歌词或完整旋律。若未联网核实近期趋势，必须写明“未核实实时趋势”，不得冒充当前热门。
    ████████████████████████████████████████████████████████████████
    """)


SEEDANCE_PROMPT_COMPOSITION_RULES = dedent("""\
    ████████ Seedance 最终提示词契约（最高优先级）████████
    最终可直接粘贴的每条视频 prompt 必须采用以下结构：

    主体：优先引用已上传的 @主体 或 @图片；只说明各参考图对应谁。参考图已经表达的外貌、服装和材质不得长篇复述。
    场景：只引用一张独立场景参考图；场景图可以带主体以锁定人物与环境比例。不要上传或引用拼接式分镜故事板、镜头曲线图、标注表格。
    音乐：默认生成经近期抖音趋势核实、与画面匹配的同类原创 BGM，并叠加对应动作和环境音效。写明具体参考曲目/热梗音乐、类型、BPM、核心音色、情绪和卡点。

    普通多镜头：使用 Shot 01 / Shot 02 编号，每个 Shot 写清景别/机位、动作事件、必要运镜和关键音效。
    固定监控/刚性安装摄像头/明确一镜到底：不使用 Shot 编号，改用单段「连续动作流程：」描述从开始到结束的完整连续事件。

    硬性规则：
    - 禁止使用 [0-3秒]、0-3s 等时间戳。普通内容用镜头数量控制节奏；固定监控和一镜到底内容禁止拆镜。
    - 描述言简意赅，不写长篇情绪渲染、同义词堆砌、摄影术语炫技或参考图已表达的内容。
    - 刚性安装摄像头相对载体的位置、朝向、高度、俯仰角和焦距全程不变，禁止独立运镜、追踪、重新构图、视角重置或第三人称机位。门载猫眼摄像头只被向屋内开启的门板带动，围绕固定合页有限连续转动；视野从对门逐渐扫过自家门框内侧并转到部分自家玄关，不得生成独立推进或错误开门方向。
    - 手持道具每一刻必须由手、手臂、身体、地面或家具支撑；拿快递后取钥匙必须写出转移承托或放地腾手的完整过程，禁止悬空、漂浮、瞬移和无支撑换手。
    - BGM 默认启用，且必须具体、可执行；禁止只写“抖音热门BGM”“流行音乐”“电子乐”。优先引用近期公开热榜中的具体曲目和艺人作为风格参考，并注明检索月份；只生成同类原创版本，不照搬完整旋律。用户明确要求不要 BGM 时，才改为只生成对应音效。
    - 真人手机视频的每条最终视频 prompt 都必须显式写入“手机物理缺陷硬约束”：中间调与暗部可见细小随机亮度颗粒、少量逐帧变化彩噪、发丝/手指/饰品/衣角运动时的方向性动态拖影、轻微焦点偏离与对焦呼吸、手持随机微抖或载体微震、滚动快门轻微形变、自动曝光/白平衡泵动、高光轻微溢出、手机降噪涂抹与平台压缩块；并明确禁止无噪点、无颗粒、全程锐利、HDR、影棚精修和稳定器般平滑。这不是电影级高清，也不是满屏粗颗粒或整幅糊化。
    - 人物动作必须避免同一手势或同一走路姿态循环；普通混剪要通过镜头方向、表情、手部动作、视线和重心变化制造自然差异。人物眼神要有眨眼和视线转移，不能长时间空洞盯镜头或盯向镜头旁边。不要只写“自然、轻松”这类空泛词，必须给出至少两种身体细节和一种视线/表情变化。
    - 参考热门曲目是为了匹配当期抖音用法，优先生成同类原创 BGM，不照搬原曲歌词或完整旋律。无法联网核实时不得冒充实时热门。
    - 优先按 720p 生成和迭代，不在 prompt 中要求 1080p/4K/8K；定稿后再外部放大。
    - 详细人物设定保留在 character_sheets，详细场景设定保留在独立场景参考图；视频 prompt 只负责引用与调度。
    ████████████████████████████████████████████████████████████████████
""")


BATCH_SHOT_RULES = dedent("""\
    要求：
    1. 为提供的 timeline 条目生成独立可用的提示词
    2. hook 段和 payoff 段强化视觉事件本身，不用空泛的史诗化修饰堆砌
    3. 普通多镜头使用 Shot 编号；检测到固定监控、刚性安装摄像头或一镜到底时，必须合并为单段「连续动作流程」，禁止 Shot 拆分、切镜和时间戳
    4. 每个 prompt 只保留生成必需的风格/色调/光影信息，已由参考图表达的内容不要重复
    5. 根据 camera_language 选择必要且可执行的运镜
    6. 标注需要角色图/独立场景图等参考素材的镜头，不生成或建议上传拼接式分镜故事板
    7. 超过15秒的段落标注拆分建议
    8. 保留 transferable_pattern 中"必须保留"的元素
    9. 默认生成具体且经近期抖音趋势核实的 BGM，并叠加动作和环境音效；仅在用户明确关闭时使用音效-only
    10. 推荐 720p 生成，定稿后再外部放大

    短片段处理策略（Seedance 最短 4 秒，极其重要）：
    - 如果某个 timeline 条目时长 < 4 秒：
      1. 优先与相邻片段合并（前一个或后一个），合并后总时长不超过 10 秒
      2. 如果无法合并（前后都已超长），则将该片段扩展到 4 秒，在 prompt 中自然延伸动作节奏
      3. 合并后的 shot 在 original_segments 字段标注原始 time_range 来源，方便后期精确剪辑
    - 每个 shot 的 duration_seconds 必须 >= 4 且 <= 10（Seedance 最佳范围 4-10s）
    - 如果原始片段刚好 4-10 秒，则 original_segments 只包含自身
    - 绝不允许输出 duration_seconds < 4 的 shot

    风格锚定要求（防止风格偏移）：
    - 从 visual_language.realism_level 判断视频风格类型
    - 从 visual_language.production_look 获取具体制作风格描述
    - 从 visual_language.skin_texture 获取皮肤质感信息
    - 从 visual_language.camera_equipment_feel 获取拍摄设备质感
    - 每个 shot 必须填写 style_anchor 字段，标注该镜头的风格锚定
    - 每个 shot 必须填写 subject_description_summary，从 timeline 对应条目的 subject_description 提取
    - 需要首帧图的 shot 必须填写 first_frame_prompt（完整的中文图片生成提示词），不需要的填空字符串

    人物描述一致性要求：
    - 利用 timeline 中每条的 subject_description 字段获取人物外貌信息
    - 首次出现的人物必须完整描述（性别、年龄段、发型发色、肤色、五官、服装、体态）
    - 后续镜头至少保留 2-3 个关键辨识特征

    动态描述要求（极其重要，防止生成出幻灯片式静态视频）：
    - 必须从 timeline 中的 subject_action 字段提取所有运动元素，在 prompt 中充分体现
    - 分镜 prompt 中必须描述三个层面的动态：
      1. 主体动作：人物在做什么（挥剑/奔跑/仰头/静立等）
      2. 怪兽/生物动作：如果镜头中有怪兽、巨兽、妖魔，必须描述它们的具体动作
         （张口咆哮/喷火/身体晃动/翅膀扑动/口腔吐出雾气等），
         不能只写"背景可见XXX"——这样生成出来怪兽是静态死物
      3. 环境受力反馈：动作对周围环境的影响
         （咆哮气流吹动头发衣物/脚步震动扬起雾气/火焰照亮岩壁等）
    - 即使人物静止，也要描述画面中所有在运动的元素（雾气翻涌/火光跳动/怪兽活动/风/水面波纹等）
    - 非固定监控内容不要全用 Static，可按原片证据选择 Handheld 或必要运镜；固定监控、门铃、车载固定机位严禁为了增加动感而添加手持微抖、Push In、Dolly In 或跟拍
    - 大气效果描述要足够强：雾气"持续翻涌"而非"弥漫"，灯笼"忽明忽暗跳动"而非"发光"
""")


def build_user_prompt(
    analysis_data: dict,
    style_hint: str | None = None,
    image_model: str = "nanobanana",
    music_mode: str = "auto",
    case_id: str | None = None,
) -> str:
    """将 analysis.json 格式化为 user prompt（分镜模式，向后兼容）。"""
    analysis_json = json.dumps(analysis_data, ensure_ascii=False, indent=2)
    style_directive = _resolve_style_directive(analysis_data, style_hint, image_model)
    music_directive = _resolve_music_generation_directive(analysis_data, music_mode)
    continuity_directives = _extract_continuity_directives(analysis_data)
    case_guidance = _resolve_case_guidance(analysis_data, case_id)
    camera_directive = "\n".join(d for d in (
        _resolve_realism_camera_directive(analysis_data, style_hint),
        _resolve_platform_safety_directive(analysis_data),
    ) if d)

    # 角色完整清单（如果一阶段提供了）
    characters_detected = analysis_data.get("characters_detected", [])
    char_detect_section = ""
    if characters_detected:
        char_detect_json = json.dumps(characters_detected, ensure_ascii=False, indent=2)
        char_detect_section = dedent(f"""\

        ████████ 一阶段检测到的完整角色清单 ████████
        以下是视频分析阶段检测到的所有角色，请确保每个角色都有对应的 character_sheets 条目：
        {char_detect_json}
        如果某个角色在 timeline 描述中未被详细提及，请根据此清单中的信息和辨识特征尽量生成角色图。
        宁可多生成不能漏生成——漏掉的角色会导致后续分镜缺少参考。
        ████████████████████████████████████████████████████████████████████
        """)

    return dedent(f"""\
    请基于以下视频分析结果，为每个 timeline 分镜生成 Seedance 2.0 提示词。

    {style_directive}
    {music_directive}
    {continuity_directives}
    {case_guidance}
    {camera_directive}
    {char_detect_section}

    分析结果：
    {analysis_json}

    {SEEDANCE_PROMPT_COMPOSITION_RULES}
    {BATCH_SHOT_RULES}
    11. 生成 prompt_versions：严格生成 A/B/C 三个版本；每版同时包含完整 character_prompt 与完整 video_prompt。A 最还原原片，B/C 默认只更换人物发型、妆容、服装和配饰，原片场景、时段、机位、画幅保持不变。每个字段必须独立可粘贴，不得写“同上/与 A 相同”。
        ⭐ 如果同一人物在视频内存在变装、前后妆造切换或两种明确状态，每版必须额外输出 character_prompts 数组，按状态逐一给出完整人物图 Prompt。第一项 label 写“装扮一（生成 @图片1）”；第二项 label 写“装扮二（上传 @图片1 后生成 @图片2）”，第二项 prompt 必须明确以 @图片1 锁定同一人物的脸型、五官间距、标志特征、肤色、身材比例、机位和场景，只改变发型/妆容/服装/配饰。video_prompt 必须同时引用 @图片1 和 @图片2。character_prompt 继续保留第一套造型，供旧结构兼容。
    12. 顶层 character_sheets 和 shots 保留 A 版兼容数据；为视频中每个独立角色生成高质量角色参考图 prompt（按 system prompt 中的角色图规范）
    13. 生成 scene_reference：只生成一张独立场景参考图，必要时带主角锁定比例，严禁分镜故事板/拼贴/标注
    14. 每个 shot 标注 character_refs 引用角色 id，标注 first_frame_required 和 first_frame_prompt
    15. 角色图 prompt 格式要求：必须是一整段连续文本，用句号分隔各部分（风格锚定→构图→面部→发型→头饰→服装→道具→体态→光影→画质→禁止项），不要用换行或分段标题
    16. ⭐ 画幅比要求：人物参考图、场景参考图、首帧图和视频 prompt 全部保持原视频画幅（参见 meta.aspect_ratio）；横屏原片不得改成 9:16 人物图
    """)


def build_single_prompt_user_prompt(
    analysis_data: dict,
    style_hint: str | None = None,
    image_model: str = "nanobanana",
    music_mode: str = "auto",
    case_id: str | None = None,
) -> str:
    """
    构建"单 prompt 模式"的 user prompt。
    适用于一次生成的完整视频，以四段式结构和 Shot 编号组织镜头。
    输出：一条无时间戳、默认含具体 BGM 与音效的 Seedance prompt + 角色参考图。
    """
    analysis_json = json.dumps(analysis_data, ensure_ascii=False, indent=2)
    style_directive = _resolve_style_directive(analysis_data, style_hint, image_model)
    music_directive = _resolve_music_generation_directive(analysis_data, music_mode)
    continuity_directives = _extract_continuity_directives(analysis_data)
    case_guidance = _resolve_case_guidance(analysis_data, case_id)
    camera_directive = "\n".join(d for d in (
        _resolve_realism_camera_directive(analysis_data, style_hint),
        _resolve_platform_safety_directive(analysis_data),
    ) if d)
    duration = analysis_data.get("meta", {}).get("duration_seconds", 15)
    aspect_ratio = analysis_data.get("meta", {}).get("aspect_ratio", "16:9")

    # 角色完整清单
    characters_detected = analysis_data.get("characters_detected", [])
    char_detect_section = ""
    if characters_detected:
        char_detect_json = json.dumps(characters_detected, ensure_ascii=False, indent=2)
        char_detect_section = dedent(f"""\

        ████████ 一阶段检测到的完整角色清单 ████████
        {char_detect_json}
        ████████████████████████████████████████████████████████████████████
        """)

    return dedent(f"""\
    请基于以下视频分析结果，生成一条完整的 Seedance 2.0 视频提示词（不是分镜，是一条 prompt）。

    ████████ 单 prompt 模式（极其重要）████████
    这个视频总时长 {duration} 秒，Seedance 可以单次生成。
    不需要拆分成多个分镜 shot，不需要生成首帧图。
    必须生成一条完整的、可直接粘贴到即梦平台使用的视频提示词。

    ⭐⭐⭐ 简洁度：Prompt 不是越长越好 ⭐⭐⭐
    single_prompt 不设最低字数，目标控制在 400-1000 字符，硬上限 1800 字符。
    主体和场景已通过参考图表达时，只做 @引用，不再复述外貌、服装、材质和环境陈设。
    删除情绪渲染、同义词堆砌、无执行价值的画质词和过度摄影术语；每句话都必须直接影响画面。

    {SEEDANCE_PROMPT_COMPOSITION_RULES}

    关键要求：
    1. 必须是一条完整、可直接粘贴的 prompt。普通多镜头用 Shot 编号；固定监控、刚性安装摄像头或明确一镜到底时只用一段「连续动作流程」，不得拆 Shot
    2. 禁止使用 [0-3秒]、0-3s 等时间戳；固定监控/一镜到底同时禁止切镜、转场、跳时和构图重置
    3. 刚性安装摄像头必须锁死其相对载体的位置、朝向、高度、俯仰角和焦距，禁止独立运镜和第三人称机位；门载猫眼摄像头只随向屋内开启的门板围绕固定合页有限连续转动，视野从对门逐渐扫过自家门框内侧并转到部分自家玄关
    4. 手持道具必须持续有真实支撑；拿快递后取钥匙必须写清转移到一侧手臂承托或先放地腾手的过程，禁止悬空、瞬移和无支撑换手
    5. 画幅比为 {aspect_ratio}；生成规格写 720p，不要求 1080p/4K/8K
    5. 主体部分引用 character_sheets 对应的角色图；详细人物设定只保留在角色图 prompt 中
    6. 场景部分建议一张独立场景参考图，必要时让场景图带主体以锁定比例；不要使用分镜故事板
    7. 音乐部分遵守 music_directive：默认生成经近期抖音趋势核实的具体同类原创 BGM 并叠加音效；用户明确关闭时才只生成音效
    8. 末尾保留：禁止任何文字、字幕、LOGO或水印

    ⭐⭐⭐ 视频连贯性与动感规则 ⭐⭐⭐
    A. 运镜连贯性：固定监控/刚性安装摄像头禁止独立运镜；普通内容若有贯穿运镜，再在相关 Shot 中简短延续。
    B. 音画节奏：audio_visual_sync 中的音乐类型、BPM 和节拍关系落实到 BGM 与人物动作；一镜到底内容不得为卡音乐而切镜。
    C. 场景连续性：同场景共享一张场景参考图；固定监控不得通过重置构图伪造新视角。
    D. 过渡方式：一镜到底内容不允许任何转场；普通多镜头只保留真正影响画面的转场方向、媒介和结果。
    E. 特效互动：简短说明特效对主体或环境的实际影响，避免悬浮贴图感。

    同时生成：
    - character_sheets：主体参考图 prompt（9:16 竖版，按角色图规范）
    - scene_reference：一张独立场景参考图 prompt（与原视频同画幅，禁止故事板/拼贴）
    - metadata 信息
    - A/B/C 三个 prompt_versions；每版含完整人物参考图与完整视频 Prompt；同一人物有前后变装时，每版必须用 character_prompts 提供两套人物图
    ████████████████████████████████████████████████████████████████████

    {style_directive}
    {music_directive}
    {continuity_directives}
    {case_guidance}
    {camera_directive}
    {char_detect_section}

    分析结果：
    {analysis_json}

    角色图 prompt 格式要求：必须是一整段完整独立文本，用句号分隔各部分。
    ⭐ 人物参考图画幅必须与原视频一致：{aspect_ratio}。场景、时段、机位与原片保持一致；B/C 默认只改人物发型、妆容、服装和配饰。
    ⭐ 每版人物图与视频 Prompt 都要写入轻微失焦、动态软化、暗部细小随机噪点、手机降噪和平台压缩；不得写“同上/与 A 相同”。
    ⭐ 变装识别：若分析中同一人物存在眼镜→无眼镜、日常妆→夜妆、换装或其他前后状态，每版除兼容字段 character_prompt 外，必须输出 character_prompts 数组。第一套生成 @图片1；第二套必须写“以用户上传的 @图片1 为身份与构图参考”并生成 @图片2，逐项锁定脸型、五官、标志特征、肤色、身材比例、场景和机位。视频 Prompt 同时引用 @图片1 与 @图片2。

    输出格式：严格输出一个 JSON 对象（不要 markdown code fence）：
    {{
      "metadata": {{
        "source_title": "string",
        "total_duration_seconds": {duration},
        "aspect_ratio": "{aspect_ratio}",
        "seedance_skill_used": boolean,
        "recommended_mode": "single_prompt",
        "abstract_pattern": "string",
        "risk_points": ["string"],
        "shot_count": 1,
        "character_count": number,
        "generation_mode": "single_prompt"
      }},
      "character_sheets": [
        {{
          "id": "char_X",
          "name": "角色名",
          "role": "主角/配角",
          "appears_in_shots": [1],
          "prompt": "完整角色参考图提示词",
          "visual_tags": ["视觉标签"]
        }}
      ],
      "scene_reference": {{
        "prompt": "一张独立场景参考图提示词，禁止故事板/拼贴/文字标注",
        "includes_subject_for_scale": true,
        "character_refs": ["char_X"],
        "usage_note": "上传为 @场景1，用于锁定环境和主体比例"
      }},
      "single_prompt": "A 版完整视频提示词（兼容字段）",
      "prompt_versions": [
        {{
          "id": "A",
          "name": "原片代表造型",
          "character_prompt": "完整人物参考图提示词；画幅/场景/机位保持原片",
          "character_prompts": [
            {{"label": "装扮一（生成 @图片1）", "prompt": "第一套完整人物参考图提示词"}},
            {{"label": "装扮二（上传 @图片1 后生成 @图片2）", "prompt": "以 @图片1 锁定同一人物与构图，只改变第二套妆造的完整提示词"}}
          ],
          "video_prompt": "完整 Seedance 视频提示词"
        }},
        {{
          "id": "B",
          "name": "人物造型变体 B",
          "character_prompt": "再次写全完整人物图；只换发型/妆容/服装/配饰",
          "video_prompt": "再次写全完整视频 prompt；原场景/画幅/机位不变"
        }},
        {{
          "id": "C",
          "name": "人物造型变体 C",
          "character_prompt": "再次写全，不引用其他版本",
          "video_prompt": "再次写全，可直接粘贴"
        }}
      ],
      "workflow_note": "生成建议"
    }}
    """)


def build_batch_user_prompt(
    global_context: dict,
    timeline_batch: list,
    batch_index: int,
    total_batches: int,
    shot_index_start: int,
    is_first_batch: bool,
    is_last_batch: bool,
    style_directive: str = "",
    music_mode: str = "auto",
    case_id: str | None = None,
) -> str:
    """为单个批次构建 user prompt。"""
    ctx_json = json.dumps(global_context, ensure_ascii=False, indent=2)
    batch_json = json.dumps(timeline_batch, ensure_ascii=False, indent=2)

    # 音乐与连贯性指令（从 analysis_data 自动提取）
    music_directive = _resolve_music_generation_directive(global_context, music_mode)
    continuity_directives = _extract_continuity_directives(global_context)
    case_guidance = _resolve_case_guidance(global_context)
    camera_directive = "\n".join(d for d in (
        _resolve_realism_camera_directive(global_context),
        _resolve_platform_safety_directive(global_context),
    ) if d)

    # 角色完整清单（如果一阶段提供了）
    characters_detected = global_context.get("characters_detected", [])
    char_detect_section = ""
    if characters_detected:
        char_detect_json = json.dumps(characters_detected, ensure_ascii=False, indent=2)
        char_detect_section = dedent(f"""\

        ████████ 一阶段检测到的完整角色清单 ████████
        以下是视频分析阶段检测到的所有角色，请确保所有批次合计覆盖每一个角色：
        {char_detect_json}
        如果某角色在当前批次的 timeline 中出现但之前批次未生成过，必须为其生成 character_sheets。
        ████████████████████████████████████████████████████████████████████
        """)

    header = dedent(f"""\
    这是分批生成的第 {batch_index}/{total_batches} 批。
    Shot index 从 {shot_index_start} 开始编号。

    {style_directive}
    {music_directive}
    {continuity_directives}
    {case_guidance}
    {camera_directive}
    {char_detect_section}

    全局视觉/风格上下文（所有批次共享）：
    {ctx_json}

    本批次需要处理的 timeline 条目：
    {batch_json}

    {SEEDANCE_PROMPT_COMPOSITION_RULES}
    {BATCH_SHOT_RULES}
    """)

    if is_first_batch:
        header += dedent("""\

        这是第一批，请同时生成：
        1. metadata 信息（source_title, total_duration_seconds, aspect_ratio, recommended_mode, abstract_pattern, risk_points, character_count）
        2. character_sheets — 为本批 timeline 中出现的所有独立角色生成角色参考图 prompt（按 system prompt 中的角色图规范）
        3. scene_reference — 从全局上下文生成一张独立场景参考图；可带主角锁定比例，禁止故事板/拼贴/文字标注

        角色图 prompt 必须使用以下固定格式（每个角色统一，所有批次必须保持一致）：
        "与原视频 meta.aspect_ratio 一致的画幅。[风格锚定]手机 Vlog 人物参考图，[构图视角]，[原片场景和机位]。[面部：脸型+眼型+眼神+眉形+鼻型+唇形唇色+肤色肤质+表情神态]。[发型：发色+长度+造型+特殊状态]。[头饰/装饰：类型+材质+位置+附属元素]。[服装从上到下：逐件描述领口开合/材质/颜色/新旧状态/污渍痕迹/布料物理状态/层叠]。[道具：外观+材质+持握方式]。[体态气质：身材体型+姿态+气质方向词]。[光影：主光+补光+色调]。[画质要求]。禁止：任何文字、字幕、LOGO、水印、多余背景元素"
        注意：prompt 必须是一整段连续文本，用句号分隔各部分，不要用换行或分段标题。
        ⭐ 人物参考图、首帧图和视频 Prompt 画幅全部与原视频一致（参见 meta.aspect_ratio）；人物图保持原片场景/时段/机位，并写入轻微失焦、动作软化、暗部细噪点、手机降噪和平台压缩。
        ⭐ 服装描述必须忠实还原 subject_description 中的实际质感（破旧的写破旧，崭新的写崭新），严禁美化。
        """)
    else:
        header += dedent("""\

        请同时生成 character_sheets — 为本批 timeline 中新出现的角色（之前批次未生成过的）生成角色参考图 prompt（按 system prompt 中的角色图规范）。
        如果本批无新角色则返回空数组 "character_sheets": []。

        角色图 prompt 必须使用以下固定格式（与第一批保持完全一致）：
        "与原视频 meta.aspect_ratio 一致的画幅。[风格锚定]手机 Vlog 人物参考图，[构图视角]，[原片场景和机位]。[面部：脸型+眼型+眼神+眉形+鼻型+唇形唇色+肤色肤质+表情神态]。[发型：发色+长度+造型+特殊状态]。[头饰/装饰：类型+材质+位置+附属元素]。[服装从上到下：逐件描述领口开合/材质/颜色/新旧状态/污渍痕迹/布料物理状态/层叠]。[道具：外观+材质+持握方式]。[体态气质：身材体型+姿态+气质方向词]。[光影：主光+补光+色调]。[画质要求]。禁止：任何文字、字幕、LOGO、水印、多余背景元素"
        注意：prompt 必须是一整段连续文本，用句号分隔各部分，不要用换行或分段标题。
        ⭐ 人物参考图、首帧图和视频 Prompt 画幅全部与原视频一致（参见 meta.aspect_ratio）；人物图保持原片场景/时段/机位，并写入轻微失焦、动作软化、暗部细噪点、手机降噪和平台压缩。
        ⭐ 服装描述必须忠实还原 subject_description 中的实际质感（破旧的写破旧，崭新的写崭新），严禁美化。
        """)

    if is_last_batch:
        header += "\n这是最后一批，请同时生成 prompt_versions 和 workflow_note。prompt_versions 必须严格包含 A/B/C 三版，每版完整写全 character_prompt 与 video_prompt；B/C 默认只改发型、妆容、服装、配饰，原片场景、时段、机位、画幅不变。不得写同上或引用其他版本。\n"

    header += dedent("""\

    输出格式：严格输出一个 JSON 对象（不要 markdown code fence）：
    {
      "character_sheets": [
        {
          "id": "char_X",
          "name": "角色名",
          "role": "主角/配角/背景角色",
          "appears_in_shots": [1, 2],
          "prompt": "完整角色参考图提示词",
          "visual_tags": ["视觉标签"]
        }
      ],
      "scene_reference": {
        "prompt": "仅第一批生成：一张独立场景参考图提示词；后续批次返回空对象",
        "includes_subject_for_scale": true,
        "character_refs": ["char_A"],
        "usage_note": "上传为 @场景1"
      },
      "shots": [
        {
          "index": number,
          "time_range": "仅供分析和后期定位，不得写入 prompt",
          "duration_seconds": 4,
          "narrative_function": "hook",
          "attention_level": 5,
          "prompt": "完整视频提示词：主体/场景/音乐 + 普通内容用 Shot、固定监控用连续动作流程；无时间戳",
          "first_frame_prompt": "完整的首帧图提示词或空字符串",
          "first_frame_required": boolean,
          "character_refs": ["char_A"],
          "asset_hints": ["素材建议"],
          "original_segments": [{"start": 0, "end": 4}],
          "style_anchor": "写实真人/超写实CG/3D渲染/动画/etc",
          "subject_description_summary": "人物外貌摘要"
        }
      ],
      "prompt_versions": [
        {
          "id": "A/B/C（仅最后一批返回三项，其他批次返回空数组）",
          "name": "版本名称",
          "character_prompt": "完整独立人物参考图 Prompt",
          "video_prompt": "完整独立视频 Prompt"
        }
      ],
      "workflow_note": "仅最后一批返回"
    }
    """)

    return header


BATCH_SIZE = 4  # 每批处理的 timeline 条目数

import re


# ─── 结果解析 ────────────────────────────────────────────────────────────────

def _try_fix_json(raw_json: str, original_error: json.JSONDecodeError) -> dict:
    """
    尝试修复 LLM 输出的常见 JSON 格式问题：
    - prompt 文本中未转义的双引号
    - 控制字符（换行、制表符在字符串内）
    - 尾部多余逗号
    """
    fixed = raw_json

    # 修复1：尝试用 strict=False 解析（允许控制字符）
    try:
        return json.loads(fixed, strict=False)
    except json.JSONDecodeError:
        pass

    # 修复2：移除尾部逗号（如 ,] 或 ,}）
    fixed = re.sub(r',\s*([}\]])', r'\1', fixed)
    try:
        return json.loads(fixed, strict=False)
    except json.JSONDecodeError:
        pass

    # 修复3：逐字符扫描，修复字符串值内的未转义双引号
    # 策略：找到 JSON 解析出错的位置，往前找到所在字符串的开头引号，
    # 把该字符串内部的裸双引号替换为转义形式
    fixed = _fix_unescaped_quotes_in_json(raw_json)
    fixed = re.sub(r',\s*([}\]])', r'\1', fixed)  # 再次清理尾部逗号
    try:
        return json.loads(fixed, strict=False)
    except json.JSONDecodeError:
        pass

    # 修复4：更激进的方式——把所有看起来像"字符串中间的引号"替换成中文引号
    # 检测模式：在 JSON 字符串值中，如果一个 " 后面不是 , : ] } 或空白+这些，就是内嵌引号
    fixed = raw_json
    # 先把所有 \n 在字符串里的替换成 \\n
    fixed = re.sub(r',\s*([}\]])', r'\1', fixed)
    try:
        # 用 Python ast.literal_eval 作为最后手段（它比 json.loads 更宽容）
        import ast
        result = ast.literal_eval(fixed)
        if isinstance(result, dict):
            return result
    except (ValueError, SyntaxError):
        pass

    # 所有修复都失败，输出详细错误信息
    err_pos = original_error.pos
    context_start = max(0, err_pos - 200)
    context_end = min(len(raw_json), err_pos + 200)
    error_context = raw_json[context_start:context_end]
    pointer_offset = err_pos - context_start
    pointer_line = " " * pointer_offset + "^^^HERE^^^"

    raise ValueError(
        f"JSON 解析失败，自动修复未成功。\n"
        f"原始错误: {original_error}\n"
        f"错误位置附近内容:\n"
        f"...{error_context}...\n"
        f"   {pointer_line}\n"
        f"常见原因: LLM 在 prompt 文本中输出了未转义的双引号。\n"
        f"建议: 重新运行，或降低 temperature 参数。"
    )


def _fix_unescaped_quotes_in_json(text: str) -> str:
    """
    逐字符扫描 JSON 文本，将字符串值内部的未转义双引号替换为中文左双引号。
    基本思路：用状态机跟踪当前是否在字符串内部。
    当发现一个 " 不是字符串的合法开头/结尾时，替换为安全字符。
    """
    result = []
    in_string = False
    i = 0
    while i < len(text):
        ch = text[i]

        if ch == '\\' and in_string:
            # 转义序列，原样保留两个字符
            result.append(ch)
            if i + 1 < len(text):
                result.append(text[i + 1])
                i += 2
            else:
                i += 1
            continue

        if ch == '"':
            if not in_string:
                # 进入字符串
                in_string = True
                result.append(ch)
            else:
                # 可能是字符串结束，也可能是内嵌裸引号
                # 判断：看后面的字符是否是 JSON 结构字符（: , ] } 或空白后跟这些）
                rest = text[i + 1:].lstrip()
                if len(rest) == 0 or rest[0] in ':,]}':
                    # 这是字符串的合法结尾
                    in_string = False
                    result.append(ch)
                else:
                    # 这是字符串内部的裸引号，替换为中文引号
                    result.append('\u201c')
            i += 1
            continue

        result.append(ch)
        i += 1

    return ''.join(result)

def parse_llm_response(response_text: str) -> dict:
    """从 LLM 响应中提取 JSON，包含自动修复常见格式错误的能力。"""
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
        raise ValueError(
            "JSON 对象不完整（很可能是 LLM 输出被 max_tokens 截断）。"
            f"原始响应长度: {len(response_text)} 字符"
        )

    raw_json = text[json_start:json_end]

    # 尝试直接解析
    try:
        result = json.loads(raw_json)
    except json.JSONDecodeError as e:
        print(f"⚠️ JSON 解析失败（{e}），尝试自动修复...")
        result = _try_fix_json(raw_json, e)

    # 检查是否只解析到了部分内容（截断后恰好闭合的情况）
    shot_count = len(result.get("shots", []))
    if shot_count <= 1 and json_end < len(text) - 50:
        print(f"⚠️ 警告：只解析到 {shot_count} 个 shot，但响应文本在 JSON 之后还有 {len(text) - json_end} 字符，可能存在截断问题")

    # 基础结构检查（宽松模式：不要求 metadata，因为分批模式下中间批次可能没有）
    # 严格的完整性验证在 generate_shot_prompts 合并后执行
    if not isinstance(result, dict):
        raise ValueError("LLM 返回的不是 JSON 对象")

    # 只检查 shots 字段存在（这是每个批次必须有的）
    if "shots" not in result and "character_sheets" not in result:
        raise ValueError("LLM 返回的 JSON 中既没有 'shots' 也没有 'character_sheets' 字段")

    return result


# ─── 主入口（兼容原有调用方式）────────────────────────────────────────────────

def _should_use_single_prompt(analysis_data: dict) -> bool:
    """
    自动判断是否应使用单 prompt 模式。
    逻辑很简单：≤15 秒就用单 prompt（Seedance 单次可生成），>15 秒必须分镜。
    不依赖 Gemini 的 recommended_mode——那个是在评估效果复杂度，不影响 prompt 组织方式。
    """
    duration = analysis_data.get("meta", {}).get("duration_seconds", 0)
    return duration <= 15


def generate_shot_prompts(
    analysis_data: dict,
    model: str | None = None,
    base_url: str | None = None,
    api_key: str | None = None,
    batch_size: int = BATCH_SIZE,
    style_hint: str | None = None,
    image_model: str = "nanobanana",
    mode: str = "auto",
    music_mode: str = "auto",
    case_id: str | None = None,
) -> dict:
    """
    输入：analysis.json 的 dict
    输出：shot_prompts dict（结构同原版，向后兼容）

    mode:
      - "auto": 自动判断（≤15秒用 single_prompt，>15秒用分镜）
      - "single": 强制单 prompt 模式
      - "storyboard": 强制分镜模式

    music_mode:
      - "auto"/"on": 默认生成经趋势核实的具体 BGM 并叠加音效
      - "off": 用户明确要求不要 BGM，只生成对应音效
    """
    skill_content = load_seedance_skill()
    system_prompt = build_system_prompt(skill_content)

    timeline = analysis_data.get("timeline", [])

    # 判断生成模式
    use_single = False
    if mode == "single":
        use_single = True
    elif mode == "storyboard":
        use_single = False
    else:  # auto
        use_single = _should_use_single_prompt(analysis_data)

    if use_single:
        duration = analysis_data.get("meta", {}).get("duration_seconds", "?")
        print(f"[shot_prompt_generator] 🎬 单 prompt 模式（视频 {duration}s，生成一条完整 Seedance 提示词）")
        user_prompt = build_single_prompt_user_prompt(
            analysis_data,
            style_hint=style_hint,
            image_model=image_model,
            music_mode=music_mode,
            case_id=case_id,
        )
        response_text = call_llm(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            model=model,
            base_url=base_url,
            api_key=api_key,
        )
        result = parse_llm_response(response_text)
        # 标记生成模式
        result.setdefault("metadata", {})["generation_mode"] = "single_prompt"

    elif len(timeline) <= batch_size:
        print(f"[shot_prompt_generator] Timeline {len(timeline)} 条，整体生成")
        user_prompt = build_user_prompt(
            analysis_data,
            style_hint=style_hint,
            image_model=image_model,
            music_mode=music_mode,
            case_id=case_id,
        )
        response_text = call_llm(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            model=model,
            base_url=base_url,
            api_key=api_key,
        )
        result = parse_llm_response(response_text)
    else:
        # 分批生成
        global_context = _extract_global_context(analysis_data)
        style_directive = _resolve_style_directive(analysis_data, style_hint, image_model)
        batches = [
            timeline[i:i + batch_size]
            for i in range(0, len(timeline), batch_size)
        ]
        total_batches = len(batches)
        print(f"[shot_prompt_generator] Timeline {len(timeline)} 条，分 {total_batches} 批生成（每批 {batch_size} 条）")

        all_shots = []
        all_characters = {}  # id -> char dict，按 id 去重
        result = {}
        shot_index = 1

        for bi, batch in enumerate(batches, start=1):
            is_first = bi == 1
            is_last = bi == total_batches

            user_prompt = build_batch_user_prompt(
                global_context=global_context,
                timeline_batch=batch,
                batch_index=bi,
                total_batches=total_batches,
                shot_index_start=shot_index,
                is_first_batch=is_first,
                is_last_batch=is_last,
                style_directive=style_directive,
                music_mode=music_mode,
                case_id=case_id,
            )

            print(f"[shot_prompt_generator] 第 {bi}/{total_batches} 批（timeline 条目 {len(batch)} 条）...")
            response_text = call_llm(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                model=model,
                base_url=base_url,
                api_key=api_key,
            )
            batch_result = parse_llm_response(response_text)

            batch_shots = batch_result.get("shots", [])
            # 重新编号 shot index，确保全局连续
            for shot in batch_shots:
                shot["index"] = shot_index
                shot_index += 1
            all_shots.extend(batch_shots)
            print(f"[shot_prompt_generator] 第 {bi} 批完成，生成 {len(batch_shots)} 个 shots")

            # 合并 character_sheets（所有批次，按 id 去重，先到先得）
            for char in batch_result.get("character_sheets", []):
                char_id = char.get("id")
                if char_id and char_id not in all_characters:
                    all_characters[char_id] = char
            batch_char_count = len(batch_result.get("character_sheets", []))
            if batch_char_count > 0:
                print(f"[shot_prompt_generator] 第 {bi} 批新增 {batch_char_count} 个角色，累计 {len(all_characters)} 个")

            # 从第一批提取 metadata 和全片唯一的场景参考图
            if is_first:
                if "metadata" in batch_result:
                    result["metadata"] = batch_result["metadata"]
                if batch_result.get("scene_reference"):
                    result["scene_reference"] = batch_result["scene_reference"]

            # 从最后一批提取 A/B/C 完整版本和 workflow_note
            if is_last:
                if "prompt_versions" in batch_result:
                    result["prompt_versions"] = batch_result["prompt_versions"]
                if "workflow_note" in batch_result:
                    result["workflow_note"] = batch_result["workflow_note"]

        result["character_sheets"] = list(all_characters.values())
        result["shots"] = all_shots

        # 更新 metadata 中的 shot_count 和 character_count
        if "metadata" in result:
            result["metadata"]["shot_count"] = len(all_shots)
            result["metadata"]["character_count"] = len(all_characters)

        # 检查角色引用完整性
        all_char_ids = set(all_characters.keys())
        all_ref_ids = set()
        for shot in all_shots:
            for ref in shot.get("character_refs", []):
                all_ref_ids.add(ref)
        missing_chars = all_ref_ids - all_char_ids
        if missing_chars:
            print(f"⚠️ 警告：以下角色在 shots 中被引用但没有对应的 character_sheets：{missing_chars}")

    # 确保 metadata 存在且有 seedance_skill_detected 字段
    result.setdefault("metadata", {})
    result["metadata"]["seedance_skill_detected"] = skill_content is not None
    # 兼容旧字段名
    if "seedance_skill_used" in result["metadata"]:
        del result["metadata"]["seedance_skill_used"]

    # 从一阶段 analysis_data 回填 LLM 可能漏掉的 metadata 字段
    meta = result["metadata"]
    a_meta = analysis_data.get("meta", {})
    a_seed = analysis_data.get("seedance_translation", {})
    a_trans = analysis_data.get("transferable_pattern", {})
    if not meta.get("source_title") or meta.get("source_title") == "untitled":
        meta["source_title"] = a_meta.get("title", "untitled")
    if not meta.get("total_duration_seconds"):
        meta["total_duration_seconds"] = a_meta.get("duration_seconds", 0)
    if not meta.get("aspect_ratio"):
        meta["aspect_ratio"] = a_meta.get("aspect_ratio", "")
    if not meta.get("recommended_mode") or meta.get("recommended_mode") == "N/A":
        meta["recommended_mode"] = a_seed.get("recommended_mode", "")
    if not meta.get("abstract_pattern") or meta.get("abstract_pattern") == "N/A":
        meta["abstract_pattern"] = a_trans.get("abstract_pattern", "")
    if not meta.get("risk_points"):
        meta["risk_points"] = a_seed.get("risk_points", [])

    # ─── A/B/C 最终交付验证 ───
    prompt_versions = result.get("prompt_versions", [])
    if not isinstance(prompt_versions, list) or len(prompt_versions) != 3:
        raise ValueError("prompt_versions 必须严格包含 A/B/C 三个完整版本")
    version_ids = [str(item.get("id", "")).upper() for item in prompt_versions if isinstance(item, dict)]
    if version_ids != ["A", "B", "C"]:
        raise ValueError(f"prompt_versions 顺序必须为 A/B/C，实际为：{version_ids}")
    forbidden_shortcuts = ("同上", "与 A 相同", "与A相同", "参考上文", "延续上文")
    for version in prompt_versions:
        for field in ("name", "character_prompt", "video_prompt"):
            value = version.get(field, "")
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"prompt_versions[{version.get('id', '?')}].{field} 不能为空")
        character_prompts = version.get("character_prompts")
        if character_prompts is not None:
            if not isinstance(character_prompts, list) or len(character_prompts) < 2:
                raise ValueError(
                    f"prompt_versions[{version.get('id', '?')}].character_prompts "
                    "必须至少包含装扮一和装扮二"
                )
            for index, item in enumerate(character_prompts, start=1):
                if not isinstance(item, dict):
                    raise ValueError(
                        f"prompt_versions[{version.get('id', '?')}].character_prompts[{index}] "
                        "必须为对象"
                    )
                for field in ("label", "prompt"):
                    value = item.get(field, "")
                    if not isinstance(value, str) or not value.strip():
                        raise ValueError(
                            f"prompt_versions[{version.get('id', '?')}]."
                            f"character_prompts[{index}].{field} 不能为空"
                        )
            if "@图片1" not in character_prompts[1]["prompt"]:
                raise ValueError(
                    f"prompt_versions[{version.get('id', '?')}] 的第二套人物图 "
                    "必须引用 @图片1 锁定人物一致性"
                )
        combined = version["character_prompt"] + version["video_prompt"]
        if character_prompts:
            combined += "".join(item["prompt"] for item in character_prompts)
        if any(shortcut in combined for shortcut in forbidden_shortcuts):
            raise ValueError(f"prompt_versions[{version['id']}] 使用了省略引用，必须完整独立写全")

    # ─── 最终验证 ───
    print("\n[shot_prompt_generator] 执行最终验证...")

    is_single_mode = result.get("metadata", {}).get("generation_mode") == "single_prompt"

    if is_single_mode:
        # 单 prompt 模式：只检查基本结构和角色
        if not result.get("single_prompt"):
            raise ValueError("单 prompt 模式但 single_prompt 字段为空")
        prompt_len = len(result["single_prompt"])
        if prompt_len > 2000:
            print(f"⚠️ 警告：single_prompt 长度 {prompt_len} 字符，超过 Seedance 2000 字符限制！需要手动精简。")
        else:
            print(f"[shot_prompt_generator] ✅ single_prompt 长度：{prompt_len}/2000 字符")
        if result.get("character_sheets"):
            print(f"[shot_prompt_generator] ✅ 角色参考图：{len(result['character_sheets'])} 个")
        print(f"[shot_prompt_generator] ✅ 单 prompt 模式验证通过")
    else:
        # 分镜模式：完整验证
        # 1. Schema validation
        validation_result = validate_shot_prompts(result)
        if not validation_result.is_valid:
            print(str(validation_result))
            raise ValueError(f"Schema validation failed with {len(validation_result.errors)} error(s)")
        if validation_result.warnings:
            print(str(validation_result))

        # 2. Character consistency check
        consistency_result = validate_character_consistency(result)
        if consistency_result.warnings:
            print("[shot_prompt_generator] Character consistency warnings:")
            print(str(consistency_result))

        # 2b. Character drift detection
        drift_result = detect_character_drift(result.get("character_sheets", []))
        if drift_result.errors:
            print("[shot_prompt_generator] Character drift errors:")
            print(str(drift_result))
            raise ValueError(f"Character drift validation failed")
        if drift_result.warnings:
            print("[shot_prompt_generator] Character drift warnings:")
            print(str(drift_result))

        # 2c. 7-dimension framework check
        dimension_result = validate_7dimension_completeness(result)
        if dimension_result.warnings:
            print("[shot_prompt_generator] 7-dimension framework checks:")
            print(str(dimension_result))

        # 3. Style anchor compliance (basic check)
        style_result = validate_style_anchor_compliance(result)
        if style_result.errors:
            print("[shot_prompt_generator] Style anchor errors:")
            print(str(style_result))
            raise ValueError(f"Style anchor validation failed with {len(style_result.errors)} error(s)")
        if style_result.warnings:
            print("[shot_prompt_generator] Style anchor warnings:")
            print(str(style_result))

        # 3b. Advanced style anchor prefix validation
        realism_level = analysis_data.get("visual_language", {}).get("realism_level")
        prefix_result = validate_style_anchor_prefix(result, realism_level)
        if prefix_result.errors:
            print("[shot_prompt_generator] Style anchor prefix errors:")
            print(str(prefix_result))
            raise ValueError(f"Style prefix validation failed")
        if prefix_result.warnings:
            print("[shot_prompt_generator] Style anchor prefix warnings:")
            print(str(prefix_result))

        # 3c. Platform compliance validation
        platform = image_model or "seedance"
        platform_result = validate_platform_compliance(result, platform)
        if platform_result.errors:
            print(f"[shot_prompt_generator] Platform ({platform}) compliance errors:")
            print(str(platform_result))
            raise ValueError(f"Platform compliance validation failed")
        if platform_result.warnings:
            print(f"[shot_prompt_generator] Platform ({platform}) compliance warnings:")
            print(str(platform_result))

        # 3d. Style consistency analysis
        style_consistency = compare_style_consistency(result)
        print(f"[shot_prompt_generator] Style consistency score: {style_consistency['consistency_score']:.1%}")
        print(f"[shot_prompt_generator] Style anchors: {style_consistency['style_anchors']}")
        if style_consistency['issues']:
            print("[shot_prompt_generator] Style consistency issues:")
            for issue in style_consistency['issues']:
                print(f"   - Shot {issue['shot']}: {issue['message']}")

    print("✅ 所有验证通过")

    return result


# ─── Markdown 报告渲染 ──────────────────────────────────────────────

def render_prompts_md(shot_prompts: dict) -> str:
    """渲染面向用户的唯一 prompts.md：A/B/C 每版紧邻人物图与视频 Prompt。"""
    meta = shot_prompts.get("metadata", {})
    versions = shot_prompts.get("prompt_versions", [])
    if not versions:
        return render_shot_prompts_md(shot_prompts)

    lines = [
        f"# {meta.get('source_title', 'untitled')} · A/B/C 完整 Prompts",
        "",
        f"> 原片画幅：{meta.get('aspect_ratio', 'N/A')}。人物参考图、视频场景、时段、机位默认保持原片；B/C 只更换人物发型、妆容、服装和配饰。",
        "",
    ]
    for version in versions:
        version_id = str(version.get("id", "?")).upper()
        name = version.get("name", "未命名版本")
        lines.extend([f"## 版本 {version_id} · {name}", ""])
        character_prompts = version.get("character_prompts")
        if isinstance(character_prompts, list) and character_prompts:
            for index, item in enumerate(character_prompts, start=1):
                label = item.get("label", f"装扮 {index}")
                lines.extend([
                    f"### 人物参考图 Prompt {index} · {label}",
                    "",
                    item.get("prompt", "").strip(),
                    "",
                ])
        else:
            lines.extend([
                "### 人物参考图 Prompt",
                "",
                version.get("character_prompt", "").strip(),
                "",
            ])
        lines.extend([
            "### 视频 Prompt",
            "",
            version.get("video_prompt", "").strip(),
            "",
        ])
    return "\n".join(lines).rstrip() + "\n"


def render_shot_prompts_md(shot_prompts: dict) -> str:
    meta = shot_prompts.get("metadata", {})
    workflow_note = shot_prompts.get("workflow_note", "")
    characters = shot_prompts.get("character_sheets", [])
    scene_reference = shot_prompts.get("scene_reference", {})

    # 构建角色 ID → 角色信息 的查找表
    char_map = {}
    for char in characters:
        char_map[char.get("id", "")] = char

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

    # 角色总览表
    if characters:
        lines += ["## 📊 角色总览", ""]
        lines.append("| 角色 ID | 名称 | 角色类型 | 出现镜头 | 需要参考图 |")
        lines.append("|---------|------|---------|---------|-----------|")
        for char in characters:
            char_id = char.get("id", "?")
            char_name = char.get("name", "?")
            char_role = char.get("role", "")
            appears = char.get("appears_in_shots", [])
            appears_str = ", ".join(f"Shot {s}" for s in appears)
            # 主角需要多角度参考图，配角建议生成
            if char_role == "主角":
                ref_needed = "✅ 必须（多角度）"
            elif char_role in ("配角", "主要角色"):
                ref_needed = "✅ 建议"
            else:
                ref_needed = "⚪ 可选"
            lines.append(f"| `{char_id}` | {char_name} | {char_role} | {appears_str} | {ref_needed} |")
        lines.append("")

    # 角色参考图详情
    if characters:
        lines += ["## 🎭 角色参考图", ""]
        for char in characters:
            char_id = char.get("id", "?")
            char_name = char.get("name", "?")
            char_role = char.get("role", "")
            appears = char.get("appears_in_shots", [])
            lines += [
                f"### {char_name}  `{char_id}`  {char_role}  出现于 Shot {', '.join(str(s) for s in appears)}",
                "",
                "```",
                char.get("prompt", ""),
                "```",
                "",
            ]
            if char.get("visual_tags"):
                lines.append(f"> 🏷️ 视觉标签：{', '.join(char['visual_tags'])}")
                lines.append("")
        lines += ["---", ""]

    # 单张场景参考图
    if scene_reference and scene_reference.get("prompt"):
        lines += [
            "## 🏞️ 场景参考图（单张）",
            "",
            "> 上传为 `@场景1`。禁止生成或上传拼接式分镜故事板。",
            "",
            "```",
            scene_reference.get("prompt", ""),
            "```",
            "",
        ]
        if scene_reference.get("usage_note"):
            lines.append(f"> 使用说明：{scene_reference['usage_note']}")
            lines.append("")
        if scene_reference.get("character_refs"):
            lines.append(f"> 比例锚定角色：{', '.join(scene_reference['character_refs'])}")
            lines.append("")
        lines += ["---", ""]

    # 单 prompt 模式
    single_prompt = shot_prompts.get("single_prompt", "")
    if single_prompt:
        lines += [
            "## 🎬 Seedance 视频提示词（可直接粘贴到即梦使用）",
            "",
            "```",
            single_prompt,
            "```",
            "",
        ]
        # 单 prompt 模式下不输出分镜
    else:
        # 分镜模式
        lines += ["## 🎬 分镜提示词", ""]

        for shot in shot_prompts.get("shots", []):
            lines += [
                f"### Shot {shot.get('index', '?')}  `{shot.get('time_range', '?')}`  `{shot.get('narrative_function', '?')}`  注意力:{shot.get('attention_level', '?')}/5",
                "",
                "```",
                shot.get("prompt", ""),
                "```",
                "",
            ]
            # 首帧图 prompt
            ffp = shot.get("first_frame_prompt", "")
            if ffp:
                lines += [
                    "**🖼️ 首帧图 Prompt：**",
                    "",
                    "```",
                    ffp,
                    "```",
                    "",
                ]

            # 角色引用
            char_refs = shot.get("character_refs", [])
            if char_refs:
                lines.append(f"> 👤 角色引用：{', '.join(char_refs)}")
                lines.append("")

            # 角色图使用指引
            if char_refs:
                lines.append("> 📌 **角色图使用指引：**")
                img_index = 1
                has_first_frame = bool(ffp)
                if has_first_frame:
                    lines.append(f"> - @图片1（首帧图）：使用上方「首帧图 Prompt」生成的首帧参考图")
                    img_index = 2
                for ref_id in char_refs:
                    char_info = char_map.get(ref_id)
                    if char_info:
                        char_name = char_info.get("name", ref_id)
                        char_role = char_info.get("role", "")
                        if char_role in ("主角", "主要角色"):
                            lines.append(f"> - @图片{img_index}（角色锚定）：`{ref_id}` {char_name} — 上传该角色参考图用于一致性锚定")
                        else:
                            lines.append(f"> - 参考：`{ref_id}` {char_name} — 可选上传角色参考图辅助一致性")
                    else:
                        lines.append(f"> - ⚠️ `{ref_id}` — 缺少角色参考图（character_sheets 中未找到）")
                    img_index += 1
                lines.append("")

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
    parser.add_argument(
        "--batch-size",
        type=int,
        default=BATCH_SIZE,
        help=f"每批处理的 timeline 条目数（默认 {BATCH_SIZE}，设大值可禁用分批）",
    )
    parser.add_argument(
        "--realism-level",
        default=None,
        choices=["photorealistic", "semi-realistic", "3d-render", "stylized", "anime", "abstract"],
        help="强制覆盖 analysis.json 中的 realism_level（当 Gemini 判断不准时使用）",
    )
    parser.add_argument(
        "--style-hint",
        default=None,
        help="用自然语言描述视频风格，会作为最高优先级注入 LLM（如 '暗黑东方仙侠真人实拍，类似网飞真人版，中式五官'）",
    )
    parser.add_argument(
        "--max-shots",
        type=int,
        default=None,
        help="只处理前 N 条 timeline（快速测试用，省 token）",
    )
    parser.add_argument(
        "--image-model",
        default="nanobanana",
        choices=["nanobanana", "seedance"],
        help="角色参考图/首帧图的目标图片生成平台（默认 nanobanana）",
    )
    parser.add_argument(
        "--aspect-ratio",
        default=None,
        help="强制覆盖 analysis.json 中的画幅比（如 16:9, 9:16, 1:1）",
    )
    parser.add_argument(
        "--mode",
        default="auto",
        choices=["auto", "single", "storyboard"],
        help="生成模式：auto=自动判断（≤15s用单prompt，>15s用分镜），single=强制单prompt，storyboard=强制分镜（默认 auto）",
    )
    parser.add_argument(
        "--music-mode",
        default="auto",
        choices=["auto", "on", "off"],
        help="BGM 模式：auto/on=默认生成具体热门 BGM+音效；off=用户明确不要 BGM，只生成音效（默认 auto）",
    )
    parser.add_argument("--video", default=None, help="原视频路径，用于可视化报告实测（默认按 downloads/ 约定自动查找）")
    parser.add_argument("--no-report", action="store_true", help="不生成 report.html 可视化报告")
    args = parser.parse_args()

    json_path = Path(args.analysis_json)
    output_dir = Path(args.output_dir) if args.output_dir else json_path.parent

    with open(json_path, encoding="utf-8") as f:
        data = json.load(f)

    # 强制覆盖 realism_level
    if args.realism_level:
        old_level = data.get("visual_language", {}).get("realism_level", "未设置")
        data.setdefault("visual_language", {})["realism_level"] = args.realism_level
        print(f"[shot_prompt_generator] ⚠️ 强制覆盖 realism_level: {old_level} → {args.realism_level}")

    # 强制覆盖 aspect_ratio
    if args.aspect_ratio:
        old_ratio = data.get("meta", {}).get("aspect_ratio", "未设置")
        data.setdefault("meta", {})["aspect_ratio"] = args.aspect_ratio
        print(f"[shot_prompt_generator] ⚠️ 强制覆盖 aspect_ratio: {old_ratio} → {args.aspect_ratio}")

    print(f"[shot_prompt_generator] 分析文件：{json_path}")
    print(f"[shot_prompt_generator] Timeline 条目数：{len(data.get('timeline', []))}")
    print(f"[shot_prompt_generator] realism_level: {data.get('visual_language', {}).get('realism_level', '未设置')}")
    if args.style_hint:
        print(f"[shot_prompt_generator] 用户风格指示：{args.style_hint}")

    # 截取前 N 条 timeline（快速测试模式）
    if args.max_shots:
        original_count = len(data.get("timeline", []))
        data["timeline"] = data.get("timeline", [])[:args.max_shots]
        print(f"[shot_prompt_generator] ⚡ 快速测试模式：只处理前 {args.max_shots} 条 timeline（共 {original_count} 条）")

    shot_prompts = generate_shot_prompts(
        data,
        model=args.model,
        base_url=args.base_url,
        batch_size=args.batch_size,
        style_hint=args.style_hint,
        image_model=args.image_model,
        mode=args.mode,
        music_mode=args.music_mode,
        case_id=output_dir.name,
    )

    # 保存 JSON
    output_dir.mkdir(parents=True, exist_ok=True)
    out_json = output_dir / "shot_prompts.json"
    out_json.write_text(json.dumps(shot_prompts, ensure_ascii=False, indent=2), encoding="utf-8")

    # 保存面向用户的唯一 Markdown 交付物
    out_md = output_dir / "prompts.md"
    out_md.write_text(render_prompts_md(shot_prompts), encoding="utf-8")

    shot_count = shot_prompts.get("metadata", {}).get("shot_count", len(shot_prompts.get("shots", [])))
    skill_used = shot_prompts.get("metadata", {}).get("seedance_skill_detected", False)
    print(f"✅ 生成完成：{out_json}")
    print(f"✅ 生成完成：{out_md}")
    print(f"   共 {shot_count} 个分镜 prompt，Seedance skill: {'✅ 已使用' if skill_used else '⚠️ 未检测到'}")

    if not args.no_report and (output_dir / "analysis.json").exists():
        from report_builder import build_report, check_summary
        try:
            path, doc = build_report(output_dir, video=Path(args.video) if args.video else None)
            print(f"📊 可视化报告：{path}（{check_summary(doc)}）")
        except Exception as e:
            print(f"⚠️  可视化报告生成失败（不影响 prompts.md）：{e}")


if __name__ == "__main__":
    main()
