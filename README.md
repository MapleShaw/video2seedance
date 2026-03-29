# Video Case Analyzer for Seedance

把优质参考视频拆成可复用的生成语法，而不是只做摘要。

## 它解决什么问题？

现在很多 AI 工具能“总结视频讲了什么”，但很难回答：

- 这条视频为什么抓人？
- 它为什么看起来高级？
- 哪些结构可以迁移到别的题材？
- 怎么把这种感觉转译成 Seedance 2.0 可执行的生成方案？

这个项目就是为这个问题做的。

---

## 核心定位

**输入：**
一个参考视频（本地路径或 URL）

**输出：**
1. 结构化 JSON 分析结果
2. Markdown 案例分析报告
3. 面向 Seedance 的生成转译建议

---

## 不做什么

- 不做自动剪辑
- 不做视频下载器
- 不负责直接产出最终成片
- 不追求影视工业级逐帧镜头分析

---

## 典型使用场景

- 拆解广告感很强的视频
- 分析爆款短视频的 hook 和 retention 机制
- 为 Seedance / 即梦生成做前期研究
- 给脚本 Agent / 分镜 Agent 提供输入依据
- 做风格迁移，而不是简单抄题材

---

## 核心输出结构

### 1. 客观观察层
- 时长、比例、镜头数
- 时间轴事件
- 画面、镜头、音画关系

### 2. 机制层
- hook 类型
- 注意力维持方式
- 节奏结构
- 情绪推进
- 高级感来源

### 3. 抽象迁移层
- 必须保留
- 可以替换
- 不建议照抄
- 抽象骨架

### 4. Seedance 转译层
- 推荐生成模式
- 提示词模板
- 参考素材建议
- 风险点

---

## 项目结构建议

```bash
video2seedance/
├─ SKILL.md
├─ README.md
├─ requirements.txt
├─ .gitignore
├─ src/
│  ├─ gemini_video_case_analyzer.py
│  ├─ prompts.py
│  ├─ schema.py
│  ├─ formatter.py
│  └─ utils.py
├─ examples/
│  ├─ sample_output.json
│  └─ sample_report.md
└─ tests/
```

---

## 工作流建议

推荐把它作为中间层使用：

参考视频
→ 案例分析器
→ 生成结构化报告
→ Seedance 提示词生成器 / 脚本器 / 分镜器
→ 视频生成与拼接

---

## Gemini CLI 适配原则

这个项目推荐用 Gemini CLI 作为视频理解引擎，但不要把它当自由聊天工具。

正确做法：
- 用固定 prompt
- 强制输出 JSON + Markdown
- 把重点放在“可迁移骨架”和“Seedance 转译”
- 如果某些效果无法纯文本复现，要明确指出

---

## 开发路线建议

### MVP
- 输入视频
- 调用 Gemini
- 输出 JSON
- 生成 Markdown 报告

### V2
- 自动检测视频基础元信息
- 分析失败时自动补齐字段
- 支持多种输出模式（fast / standard / deep）

### V3
- 接 Script Agent
- 接 Storyboard Agent
- 接 Seedance Prompt Generator

---

## 为什么值得做？

因为“能看懂视频”不稀缺，  
**“能把视频拆成可复用的生成结构”才稀缺。**

这玩意儿不是玩具，而是 AI 视频工作流里真正有复利的中间层。
