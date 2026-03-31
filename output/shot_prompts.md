# 分镜提示词计划：暗黑东方奇幻视觉流：鬼魅行者

> **Seedance Skill**：✅ 已检测到，按官方规范生成
> **推荐模式**：multi-stage
> **抽象骨架**：巨物恐怖 + 极简人物主体 + 节奏型快剪

---

## 工作流说明

生成顺序建议：① 准备首帧参考图（用于 hook 段） → ② 按 shots 列表逐条在即梦生成 3-5s 片段 → ③ 按 rhythm_structure.pattern 节奏卡点剪辑拼接

## ⚠️ 风险点

- 手部姿态在快剪下的不稳定性
- 生物模型与角色比例失调

---

## 分镜提示词

### Shot 1  `0s-2s`  `hook`  注意力:5/5

```
2秒，UE5渲染，电影级VFX，8K超清，Dark Fantasy、Oriental Gothic、Cinematic Lighting、Hyper-detailed风格，Crimson Red+Obsidian Black+Pale Fog Grey色调，High contrast+Rim lighting光影，
全片统一的体积雾弥散效果，高饱和点缀色彩策略，
0-2秒：古风少女执红伞对视巨型枯骨巨兽，静止对峙，缓慢推近 + Static, Slow tracking, Zoom-in，Misty bamboo forest、Desolate mountain背景，Exquisite traditional costume，Demonic horns，Blood stains，Ancient paper/scrolls，前2秒静止对峙制造张力，镜头缓慢推近；
光影：高对比逆光+体积雾弥散（光源层），雾气柔化高光同时强化阴影对比（光行为层），Crimson Red，Obsidian Black，Pale Fog Grey（色调层）。
禁止：任何文字、字幕、LOGO或水印
```

> 💡 建议准备首帧参考图（@图片1）以锁定角色外貌
> 💡 角色需要：Exquisite traditional costume、Demonic horns

### Shot 2  `2s-60s`  `build`  注意力:4/5

```
15秒，Dark Fantasy、Oriental Gothic、Cinematic Lighting、Hyper-detailed风格，Crimson Red+Obsidian Black+Pale Fog Grey色调，High contrast+Rim lighting光影，
0-15秒：多场景切换：送葬队伍、魔兽咆哮、飞天神禽、法术符咒，持续变动与冲突，快剪、摇移 + Static, Slow tracking, Zoom-in，Misty bamboo forest、Desolate mountain，Blood stains、Ancient paper/scrolls，体积雾弥散，High contrast，Rim lighting；
禁止：任何文字、字幕、LOGO或水印
```

> 💡 建议准备首帧参考图（@图片1）以锁定角色外貌
> 💡 角色需要：Exquisite traditional costume、Demonic horns
> 💡 ⚠️ 本段时长58s，超出单次生成上限15s，建议拆为4段

---

## 变体方向

### Cyber-Gothic — 科技与废土结合

沿用「红黑配色、巨型生物结构」，替换「古装换机甲、竹林换废弃金属城市」
