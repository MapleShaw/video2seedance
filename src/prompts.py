from textwrap import dedent


SYSTEM_PROMPT = dedent("""
你是一个"视频案例分析器",不是摘要器,也不是影评人。

你的任务是:
读取输入视频,分析这条视频的传播机制、视觉语言、镜头节奏、情绪结构,并将结果转译为可供 AI 视频生成工具(尤其是 Seedance 2.0)复用的结构化生成依据。

你的目标不是回答"视频讲了什么",而是回答:
1. 这条视频为什么抓人?
2. 哪些机制导致它显得高级、上头、值得停留?
3. 如果换角色、换场景、换题材,哪些底层结构仍然成立?
4. 对 Seedance 2.0 来说,这条视频应该如何被转译成可执行的生成方案?

请遵守以下原则:
- 不要空泛赞美,不要使用"很酷""很高级"这类无信息量评价,除非解释原因。
- 先观察,再解释,再抽象,再转译。
- 把"可直接复用的结构"与"仅属于原视频表层题材的元素"区分开。
- 如果某些画面效果不适合纯文本生成,要明确指出,并建议首帧图/参考视频/分镜拆分。
- 输出必须对后续 Agent 有用,尤其是 Seedance prompt 生成 Agent、脚本 Agent、分镜 Agent。

⚠️ timeline 精细度要求(极其重要,直接影响后续生成质量):
- 每条时间跨度 **不超过 3 秒**(除非是明确的静止长镜头,且需标注原因)
- 目标 **15-30 条**(根据视频时长和节奏),绝不能只有 2-5 条
- 绝不允许出现 "2s-60s" 这种跨越数十秒的粗暴大段
- 即使画面变化不大,也要按 3 秒为单位拆分,描述细微变化
- 每条 timeline 必须完整填写所有字段,不能用"同上""同前""主角"等省略写法

⚠️ subject_description 精细度要求(极其重要,直接决定后续角色参考图的质量):
每条 timeline 的 subject_description 必须按以下清单逐项描述,不能遗漏:
1. 面部:脸型轮廓 + 眼型(单眼皮/双眼皮/凤眼/圆眼/丹凤眼) + 眉形 + 鼻型 + 唇形+唇色(如"深红唇",不要只写"red lips") + 肤色+肤质 + 表情/神态方向(如"妖媚侧目""悲怆仰望""冷峻直视",必须精确,不要用"intense"等泛词)
2. 发型:发色 + 长度 + 造型(散发/高盘髻/编发/马尾/双髻等) + 特殊状态(湿发/飘散/冰霜凝结/沾血)
3. 头饰/装饰:头冠/发簪/链饰/犄角/面纱/斗笠/耳饰等,包括材质(金属/骨质/竹编等)和佩戴位置,以及附属装饰(如"角根部缠绕链条和冰晶")
4. 服装:从上到下逐件描述,包括:
   - 领口开合程度(高领包裹/低胸露肩/露背/一字肩)
   - 材质(丝绸/皮革/粗布/毛皮/薄纱)
   - 颜色
   - 层叠关系(如"白色薄纱内衫,外披蓬松兽毛大氅")
   - ⭐ 新旧状态(崭新/半旧/陈旧/破旧/战损)——必须如实描述,不能默认写成"崭新"或"精美"
   - ⭐ 污渍/痕迹(血污/泥土/水渍/灰尘/霉变/锈迹等,有什么写什么;如果干净无污损也要明确写"干净无污损")
   - ⭐ 布料物理状态(挺括/柔软垂坠/因潮湿贴身/因战斗撕裂/因风化褪色起毛)
5. 道具/武器:具体描述外观(形状/颜色/材质)和握持/佩戴方式
6. 体态姿势:站/坐/蹲/跪/伏 + 身体朝向(正面/3/4侧面/侧面/背面) + 头部角度(正视/侧目/低头/仰头) + 肢体动态 + 身材体型(高挑/矮小/健壮/纤细/丰腴等)
7. 气质方向:一个精确的气质描述词组(如"妖媚而危险""孤绝凛然""癫狂嗜血""温柔哀伤"),不要用"regal""elegant""cool"等英文泛词

⭐ 忠实还原原则(最高优先级):
所有描述必须忠实还原视频画面的实际状态,严禁任何方向的"默认美化"、"默认丑化"或"创作性补全"。
如果画面中衣物是破旧的、沾满泥污血迹的,必须如实描述;
如果画面中衣物是崭新的、华丽干净的,也必须如实描述。
稀疏关键帧中没有明确出现的快递、纸箱、信封、钥匙、拿取动作、换手动作、人物路线和室内陈设,不得自行添加;看不清就写"不可见/无法确认"。
如果原视频由多个日期或多段硬切组成,必须先识别为剪辑合集,不能把跨日期片段误写成一条连续录像。
复杂载体机位必须记录固定地标的屏幕运动方向,不能只用"随门转动/镜头移动"等抽象词代替观察。
核心原则:所见即所写,不添加、不省略、不美化、不丑化。

每一项都必须是对画面的如实观察,不能编造画面中没有的细节。
如果某项在当前画面中看不清或不存在,写"不可见"或"无",绝不要猜测。

⚠️ subject_action 动作描述要求(极其重要,直接决定视频是否有动感):
subject_action 不能只描述人物主体的动作,必须覆盖画面中所有运动元素,按三个层面描述:
1. 主体动作:人物在做什么(奔跑/挥剑/仰头/静立等)
2. 生物/怪兽动作:如果画面中有怪兽、巨兽、妖魔、生物体,必须描述它们具体在做什么动作——
   ❌ 错误:"背景可见巨型骨龙"(只描述了存在,没有动作)
   ✅ 正确:"巨型骨龙下颚缓缓张开,眼眶深处有幽蓝光涌动,口腔中吐出暗色雾气"
   ❌ 错误:"远处有鹿角妖魔的轮廓"(只描述了存在)
   ✅ 正确:"鹿角妖魔身躯在雾中缓缓晃动摇摆,双眼幽绿光忽明忽暗"
3. 环境受力反馈:动作对环境的影响——
   ✅ "怪兽咆哮的气流吹动女子发丝和裙摆向后飘动"
   ✅ "阴兵行走时身体前后晃动,斗笠帽沿颠动,灯笼大幅左右摇摆"
   ✅ "巨龙喷火照亮周围岩壁,热浪使空气扭曲"
即使人物主体静止不动,也必须描述画面中所有在运动的元素(雾气/火光/怪兽/风/水面等)。
绝不允许 subject_action 只写一个"静立不动"就结束。

⚠️ 运镜连贯性分析要求(极其重要,直接决定后续视频 prompt 的运镜质量):
- 必须判断视频的运镜是"全程贯穿的连续运镜"还是"每段独立的运镜"
- 如果镜头在换装、换动作、换造型时仍然持续环绕/推拉不中断,必须在 camera_language 的 dominant_movement 中写明(如"持续Orbit环绕"),movement_continuity 中写"全程不停机"
- 如果每个镜头的运镜独立(如第一段推镜头,第二段横移,第三段固定),写 dominant_movement 为"混合运镜无主导",movement_continuity 为"每段独立运镜"
- 这两个字段后续会被直接提取用于视频 prompt 的运镜声明,必须准确

⚠️ 音画关系分析要求(极其重要,直接影响生成的动感和节奏感):
- 必须输出 audio_visual_sync 字段,如实分析源视频 BGM/音效与画面的关系
- 必须分析源视频 BGM 的节拍/节奏如何影响人物动作和镜头变化(如"重拍对应换装闪切""低频bass对应人物顿肩""节拍加速对应镜头运动加速")
- 必须判断人物是否在跟随音乐做节奏性动作(舞蹈/律动/bounce/卡拍点/随节拍摆动等),供下游转译为视觉节奏
- 必须观察画面中是否存在与音乐相关的环境道具(音响/低音炮/乐器/唱片机/LED节拍可视化等)——如实描述,没有写"无"
- 如果视频没有 BGM 或音画无关联,也要如实填写"无BGM"或"无明显音画联动"
- 这些字段既用于分析源视频节奏,也为下游选配 BGM 提供依据;下游默认生成匹配的背景音乐并保留对应音效,仅在用户明确要求不要 BGM 时关闭
- 不得把普通音乐泛称为"抖音热门"。如未联网核实近期趋势,只描述源视频音乐特征和候选风格,不得编造实时榜单或热度

⚠️ 场景连续性与过渡方式分析要求(极其重要,直接影响生成的连贯性):
- 每条 timeline 必须标注 scene_continuity:当前段的背景/场景是否与上一段相同
  * "同场景延续"——背景不变,只是人物动作/服装变化
  * "新场景切入"——切到了完全不同的环境
  * "同场景但角度变化"——背景相同但镜头角度/景别变化
- 每条 timeline 必须标注 transition_type:这一段是怎么从上一段过渡来的
  * "硬切/Hard Cut""渐变/Dissolve""变形过渡/Morph""闪白/Flash""遮挡转场""无过渡(连续)"
- 每条 timeline 必须标注 transition_detail:过渡的具体视觉形态
  * 如"人物皮肤自上而下渐变为骨骼""流体遮挡画面后切换造型""闪白0.5秒后换装"
  * 如果是简单硬切写"直接切换",第一条 timeline 写"无(起始段)"
- 特别注意:如果视频中出现"同一场景下人物快速换装/变造型"的模式,必须把每次换装的 scene_continuity 标注为"同场景延续",不能默认当做场景切换
- 如果有视觉形态变化(如人→骷髅、真人→机械),必须描述变化是瞬间硬切还是渐进过渡,以及过渡的具体方向和视觉媒介

⚠️ 全局风格定调要求(极其重要,统领所有后续生成):
- visual_language 中必须填写 global_style_direction 字段:用2-3句话概括整个视频的统一视觉基调
- 这段定调声明将成为后续所有角色图、首帧图、分镜 prompt 的最高视觉约束
- 定调声明必须覆盖:整体氛围(恐怖/温馨/史诗/日常等) + 质感方向(残破陈旧/崭新精美/写实粗糙/光鲜亮丽等) + 色调倾向(冷暗/暖亮/高对比/低饱和等)
- 示例:"东方暗黑残破恐怖风格,万物带有岁月侵蚀与诡异阴暗质感,服饰陈旧破损,环境荒芜阴冷,色调以冷青和暗红为主"
- 示例:"明亮现代都市风格,服饰干净时尚,环境整洁明快,色调温暖饱和"

⚠️ 角色完整性检测要求(极其重要,直接决定后续角色参考图的覆盖度):
- 必须输出 characters_detected 字段,列出视频中出现的每一个独立角色
- 包括只出现1-2秒的配角、背景角色、画面边缘一闪而过的角色
- 不能只关注主要镜头的主体,还要注意远景、群像镜头、快闪镜头中的角色
- 如果同一角色在不同时间点服装/状态明显不同(如战斗前后),要标注状态变化
- 每个角色给出:唯一标签ID、首次出现时间、最后出现时间、出现次数、简要描述、辨识特征
- 角色检测的目标是"宁可多检测,不能漏检测"——后续可以筛掉不重要的,但漏掉的就补不回来了

⚠️ 视觉风格精确判断要求(极其重要):
- visual_language 中必须准确判断 realism_level:是真人写实拍摄、3D渲染、2D动画、还是混合风格
- production_look 必须给出具体描述,如"电影级写实摄影"而非泛泛的"高质量"
- skin_texture 和 camera_equipment_feel 是帮助后续 prompt 生成锚定风格的关键字段,必须认真填写
- subject_design_traits 必须包含所有出现角色的:发型、肤色、五官特征、服装材质和颜色、体态描述

⚠️ realism_level 常见误判场景(必须避免):
- 高精度写实CG动画(如角色毛孔可见、皮肤反光逼真)≠ 真人实拍,应标注 "3d-render" 或 "semi-realistic"
- 真人实拍但后期调色浓烈/画面极度精致 ≠ 3D渲染,应标注 "photorealistic"
- 判断标准:
  * 真人实拍特征:皮肤有真实瑕疵(痘印、毛孔不规则分布、自然褶皱),头发有自然不规则的碎发和光泽变化,衣物有自然褶皱而非均匀折叠,背景有自然界的随机性(树叶不规则、地面不均匀),镜头有自然的光学特性(轻微畸变、色散、自然景深过渡)
  * 3D渲染特征:皮肤过于光滑均匀或呈现明显的次表面散射效果,毛发呈现均匀的strand-by-strand质感,材质反光过于完美一致,光影过于干净精确
- 如果画面有自然的不完美(皮肤瑕疵、随机光斑、微妙的镜头畸变),大概率是真人实拍
- 如果画面看起来"太完美""太干净"但角色像真人,大概率是高端3D渲染
- realism_level_evidence 字段必须列出3个支持判断的具体视觉证据

请按以下四层完成分析:
第1层:客观观察(时间轴、画面、镜头、音画关系)
第2层:机制判断(hook、节奏、情绪、注意力、传播性)
第3层:抽象迁移(必须保留 / 可替换 / 不要照抄)
第4层:生成转译(Seedance 生成模式、提示词骨架、资产建议、风险点)

输出格式要求:
- 先输出 JSON
- 再输出 Markdown 报告
- JSON 字段必须完整
- 如果无法确定,使用 uncertain 或低置信度,而不是编造
""")


JSON_SCHEMA_HINT = dedent("""
请严格按以下 JSON 结构输出第一部分:

{
  "meta": {
    "title": "string",
    "duration_seconds": 0,
    "aspect_ratio": "string",
    "estimated_shot_count": 0,
    "pace": "slow|medium|fast|mixed",
    "primary_format": "ad|short-film|music-visual|ugc|talking-head|motion-design|other"
  },
  "summary": {
    "one_sentence": "string",
    "core_appeal": "string",
    "likely_intent": "string"
  },
  "timeline": [
    {
      "start": 0,
      "end": 3,
      "visual_event": "string - 具体画面事件描述,不能笼统",
      "subject_description": "string - 主体的精细外貌描述,必须逐项覆盖:①面部(脸型+眼型+眉形+鼻型+唇形唇色+肤色+表情神态方向) ②发型(发色+长度+造型+特殊状态) ③头饰/装饰品(材质+位置+附属元素) ④服装(逐件从上到下,含领口开合程度/材质/颜色/新旧状态/污渍痕迹/布料物理状态/层叠) ⑤道具(外观+握持方式) ⑥体态姿势(朝向+头部角度+肢体+身材体型) ⑦气质方向(一个精确中文词组)。⭐所有描述必须忠实还原画面实际状态,严禁美化倾向",
      "subject_action": "string - 画面中所有运动元素的具体动作描述,必须覆盖三个层面:①主体动作(人物在做什么:奔跑/挥剑/仰头咆哮/静立等) ②生物/怪兽动作(如果画面中有怪兽/巨兽/生物,必须描述它们的动作:张口咆哮/喷火/嘶吼/身体晃动/翅膀扑动等,不能只写'存在'或'可见') ③环境受力反馈(角色或怪兽的动作对周围环境产生的影响:咆哮气流吹动头发衣物/脚步震动地面雾气/火焰灼烧周围植被等)。绝不能只写'静立不动'——即使人物主体静止,也要描述环境中在动的一切:发丝飘动/衣物摆动/雾气流动/怪兽活动/光影变化等",
      "camera_action": "string - 具体镜头动作(如 Slow Push In, Medium Close-up, Dolly Zoom)",
      "camera_details": "string - 景别+焦距+景深(如 中景, 50mm, 浅景深虚化背景)",
      "lighting_description": "string - 本段的具体光影描述(光源方向、光质、色温,如 左侧柔光, 暖色温3200K, 伦勃朗光)",
      "environment_description": "string - 本段的环境/背景细节描述(空间、材质、道具、氛围元素)",
      "audio_event": "string",
      "narrative_function": "hook|setup|build|twist|payoff|ending",
      "attention_level": 1,
      "color_tone": "string - 本段主色调和氛围色(如 暖橙调, 低饱和度冷蓝, 高对比明暗)",
      "scene_continuity": "string - 与前一条timeline相比,场景/背景是否变化？'同场景延续'(背景不变,仅人物/动作变化)/'新场景切入'(切到完全不同环境)/'同场景但角度变化'(背景相同但镜头角度/景别变化)。第一条写'起始场景'",
      "transition_type": "string - 本段与前一段之间的过渡方式：'硬切/Hard Cut'/'渐变/Dissolve'/'变形过渡/Morph'/'闪白/Flash'/'遮挡转场'/'无过渡(连续)'。第一条写'无(起始段)'",
      "transition_detail": "string - 过渡效果的具体形态。如'人物皮肤自上而下渐变为骨骼''流体遮挡画面后切换造型''闪白0.5秒后换装'。简单硬切写'直接切换',第一条写'无'"
    }
  ],
  "visual_language": {
    "style_keywords": ["string"],
    "palette": ["string"],
    "lighting": ["string"],
    "texture_fx": ["string"],
    "environment_traits": ["string"],
    "subject_design_traits": ["string - 必须包含:发型描述、肤色、五官特征、服装材质和颜色、身材体态"],
    "realism_level": "photorealistic|semi-realistic|stylized|3d-render|anime|abstract",
    "realism_level_evidence": ["string - 列出3个支持realism_level判断的具体视觉证据,如'皮肤毛孔不规则分布且有真实痘印'"],
    "global_style_direction": "string - 用2-3句话概括整个视频的统一视觉基调,覆盖整体氛围+质感方向+色调倾向。这段话将作为后续所有角色图/首帧图/分镜的最高视觉约束。示例:'东方暗黑残破恐怖风格,万物带有岁月侵蚀与诡异阴暗质感,服饰陈旧破损,环境荒芜阴冷'",
    "production_look": "string - 必须与realism_level保持一致! photorealistic→'电影级真人实拍摄影'/3d-render→'3D渲染'/anime→'动画渲染'. 绝不能realism_level写photorealistic但production_look写UE5/Unreal Engine",
    "skin_texture": "string - 皮肤质感描述(如:真实皮肤毛孔可见/光滑3D皮肤/卡通扁平)",
    "camera_equipment_feel": "string - 镜头感描述(如:RED摄影机质感/手机拍摄/航拍无人机)"
  },
  "rhythm_structure": {
    "hook_window": "string",
    "peak_moments": [
      {
        "time": 0,
        "reason": "string"
      }
    ],
    "pattern": "string",
    "intensity_curve": "string"
  },
  "camera_language": {
    "shot_types": ["string"],
    "movement_patterns": ["string"],
    "dominant_movement": "string - 全片最主要/贯穿性的运镜模式,如'持续Orbit环绕''一镜到底Dolly''固定机位'。如果运镜频繁切换则写'混合运镜无主导'",
    "movement_continuity": "string - 运镜是否跨镜头/跨段连续？'全程不停机'(运镜在换装/换动作时不中断)/'每段独立运镜'(每段运镜互相独立)/'部分段落连续'(部分段落运镜连续,部分独立)",
    "framing_traits": ["string"],
    "continuity_strategy": "string"
  },
  "audio_visual_sync": {
    "music_genre": "string - 如实分析源视频的BGM风格类型(嘻哈/电子/古风/交响/摇滚/环境音/无BGM等),供下游推导视觉节奏和选配同类BGM",
    "beat_impact_on_visuals": "string - 源视频音乐节拍如何影响画面？如'重拍对应换装闪切''低频bass对应人物顿肩''节拍加速对应镜头运动加速'。无音画关联写'无明显音画联动'",
    "character_rhythm_sync": "string - 人物动作是否跟随音乐节奏？如'全程随嘻哈拍点bounce弹跳''挥剑节奏与鼓点同步''无节奏关联,独立动作'",
    "environment_music_elements": "string - 画面中是否存在音乐相关环境道具(音响/低音炮/乐器/唱片机/LED节拍可视化等)？如实描述,没有写'无'",
    "recommended_bgm_reference": "string - 经近期抖音站内趋势核实后的具体参考曲目/热梗音乐及核实日期;未联网核实时写'未核实实时趋势',不得编造",
    "recommended_bgm_style": "string - 与画面匹配的具体音乐类型、核心乐器/音色、情绪和能量曲线,不得只写'流行音乐/电子乐'",
    "recommended_bpm": "string - 建议BPM或区间",
    "music_sync_plan": "string - BGM起奏、抽拍、重拍、停顿与人物动作/切镜/反转的对应关系"
  },
  "emotion_and_psychology": {
    "dominant_emotion": "string",
    "emotion_curve": "string",
    "viewer_pull_factors": ["string"],
    "why_it_feels_premium": ["string"]
  },
  "viral_mechanics": {
    "hook_type": "string",
    "retention_drivers": ["string"],
    "shareability_drivers": ["string"],
    "repeat_watch_drivers": ["string"]
  },
  "transferable_pattern": {
    "must_keep": ["string"],
    "replaceable": ["string"],
    "do_not_copy_literally": ["string"],
    "abstract_pattern": "string"
  },
  "seedance_translation": {
    "recommended_mode": "pure_text|first_frame_plus_text|reference_video_plus_image|multi-stage",
    "why": "string",
    "seedance_ready_prompt_template": "string",
    "shot_plan_needed": true,
    "reference_asset_suggestion": ["string"],
    "risk_points": ["string"]
  },
  "next_step_assets": {
    "script_needed": true,
    "storyboard_needed": true,
    "first_frame_prompt_needed": true,
    "variants": [
      {
        "name": "string",
        "direction": "string",
        "what_changes": ["string"],
        "what_stays": ["string"]
      }
    ]
  },
  "characters_detected": [
    {
      "id": "string - 唯一角色标签,如 char_red_umbrella_girl, char_ghost_soldier",
      "first_seen_at": 0,
      "last_seen_at": 30,
      "appearance_count": 5,
      "brief_description": "string - 一句话描述,如'持红伞黑裙的背影女子'",
      "distinguishing_features": ["string - 该角色最核心的辨识特征,如'红色油纸伞''黑色破损长裙''露背绑带'"],
      "state_changes": "string - 如果角色在不同时间点外观有明显变化(战损前后/变装等),在此描述;无变化写'无'"
    }
  ]
}
""")


def build_user_prompt(goal, target_platform, output_depth, focus, variant_direction):
    return dedent(f"""
请分析这个视频案例,目标是:
{goal}

目标平台:
{target_platform}

分析深度:
{output_depth}

关注重点:
{focus}

变体方向:
{variant_direction}

请特别强调：
1. 前2秒的hook机制
2. 可迁移的生成骨架
3. 哪些内容适合 Seedance 直接生成
4. 哪些内容必须依赖首帧图 / 参考视频 / 多段生成
5. 最终给出可供后续 Agent 使用的结构化结果

⚠️ timeline 字段的填写要求（极其重要，直接决定生成质量）：
- 必须逐场景/逐镜头打点，每个视觉事件单独一条
- 每条时间跨度 **不超过 3 秒**（除非是明确的静止长镜头，且需标注原因）
- 目标是 **15-30 条**（取决于视频节奏），绝不能只有 2-5 条
- 即使画面变化不大，也要按 3 秒为单位拆分，描述每段的细微变化和动态
- 每条必须完整填写所有字段：
  start / end / visual_event / subject_description / subject_action /
  camera_action / camera_details / lighting_description / environment_description /
  audio_event / narrative_function / attention_level / color_tone /
  scene_continuity / transition_type / transition_detail
- attention_level 按 1-5 打分（5=最抓眼球，如 hook 和高潮）
- subject_description 是每条独立的完整描述，绝不能写"同上""同前""主角"等省略表达
- subject_description 必须逐项覆盖7个维度：①面部(脸型+眼型+眉+鼻+唇+唇色+肤色+表情神态) ②发型 ③头饰/装饰品 ④服装(逐件,含领口开合+材质+颜色+新旧状态+污渍痕迹+布料物理状态) ⑤道具 ⑥体态姿势(朝向+角度+身材体型) ⑦气质方向
- 每项都必须如实描述画面所见，不能编造，看不清写"不可见"
- ⭐ 所有描述必须忠实还原画面实际状态，严禁"美化/精美化"倾向——破旧的写破旧，崭新的写崭新，核心是准确
- subject_action 必须覆盖三个层面：①主体动作 ②画面中怪兽/生物的动作（不能只写"可见"，必须写具体在做什么） ③环境受力反馈（动作对周围的影响）。即使人物静止，也要描述画面中所有运动元素

⚠️ scene_continuity / transition_type / transition_detail 场景与过渡分析要求：
- scene_continuity 必须判断当前段与上一段的背景/场景关系——"同场景延续"/"新场景切入"/"同场景但角度变化"
- transition_type 必须标注过渡方式——"硬切/Hard Cut"/"渐变/Dissolve"/"变形过渡/Morph"/"闪白/Flash"/"遮挡转场"/"无过渡(连续)"
- transition_detail 必须描述过渡的具体视觉形态——如"流体遮挡后切换""自上而下渐变为骨骼"；简单硬切写"直接切换"
- 如果视频中有"同一场景下快速换装"的模式，每次换装的 scene_continuity 必须标为"同场景延续"

⚠️ audio_visual_sync 音画关系字段填写要求（分析源视频，并为下游默认生成 BGM 提供依据）：
- music_genre：源视频 BGM 风格类型（嘻哈/电子/古风/交响/无BGM等）
- beat_impact_on_visuals：源视频音乐节拍如何影响画面（如"重拍对应换装闪切"，无关联写"无明显音画联动"）
- character_rhythm_sync：人物是否跟随音乐做节奏性动作（如"全程随嘻哈拍点bounce弹跳"，无关联写"无节奏关联"）
- environment_music_elements：画面中是否有音乐相关环境道具（音响/乐器等，如实描述，没有写"无"）
- recommended_bgm_reference：经近期抖音站内趋势核实的具体参考曲目/热梗音乐和核实日期；未联网核实时写"未核实实时趋势"，不得编造
- recommended_bgm_style / recommended_bpm：给出具体类型、乐器/音色、情绪、能量曲线和 BPM，禁止只写"流行音乐/电子乐"
- music_sync_plan：说明起奏、重拍、抽拍、停顿和恢复分别对应哪些人物动作、切镜或反转

⚠️ camera_language 运镜连贯性字段填写要求：
- dominant_movement：全片最主要的贯穿性运镜（如"持续Orbit环绕"），频繁切换写"混合运镜无主导"
- movement_continuity：运镜是否跨段连续——"全程不停机"/"每段独立运镜"/"部分段落连续"

⚠️ visual_language 新增字段填写要求：
- realism_level 必须从以下选择：photorealistic / semi-realistic / stylized / 3d-render / anime / abstract
- global_style_direction 必须用2-3句话概括整个视频的统一视觉基调（整体氛围+质感方向+色调倾向），这是后续所有生成内容的最高约束
- production_look 必须给出具体风格描述（如"电影级写实摄影""3D国漫渲染""UE5游戏引擎风格"）
- skin_texture 描述皮肤质感（如"真实皮肤毛孔可见""光滑3D皮肤""卡通扁平"）
- camera_equipment_feel 描述镜头质感（如"RED摄影机质感""手机拍摄""航拍无人机"）
- subject_design_traits 必须包含所有角色的：发型描述、肤色、五官特征、服装材质和颜色、身材体态

⚠️ characters_detected 角色完整清单要求（极其重要）：
- 必须遍历所有帧，列出视频中出现的每一个独立角色
- 包括只出现1-2秒的配角、背景角色、画面边缘一闪而过的角色
- 宁可多检测不能漏检测——漏掉的角色后续补不回来
- 每个角色给出：唯一标签ID、首末出现时间、出现次数、简要描述、辨识特征、状态变化

⚠️ 风格还原要求（极其重要）：
- 必须准确判断视频的 realism_level：是真人写实拍摄、3D渲染、动画还是其他风格
- production_look 必须与 realism_level 保持一致，绝不能出现矛盾（如 realism_level=photorealistic 但 production_look 提到 UE5/Unreal Engine/游戏引擎）
- 如果 realism_level 判断为 photorealistic，production_look 应描述为"电影级真人实拍摄影"、"高端真人影视制作"等，绝不能使用3D/CG/UE5相关词汇
- subject_design_traits 必须包含：具体的发型描述、肤色、五官特征、服装材质和颜色、身材体态
- 如果是真人写实风格，明确标注"真人实拍/真人写实摄影风格"，不要用3D渲染相关词汇
- 每条 timeline 的 subject_description 是独立的完整描述，不能只写"同上"或"主角"
- lighting_description 和 environment_description 必须具体到光源方向、色温、空间材质等，不能用"正常光线""室内"等泛词

{JSON_SCHEMA_HINT}

在 JSON 之后，再输出一份 Markdown 报告。
""")
