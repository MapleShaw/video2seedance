def render_markdown_stub(data: dict) -> str:
    summary = data.get("summary", {})
    viral = data.get("viral_mechanics", {})
    transferable = data.get("transferable_pattern", {})
    seedance = data.get("seedance_translation", {})

    return f"""# 视频案例分析报告\n\n## 1. 一句话结论\n{summary.get('one_sentence', 'uncertain')}\n\n## 2. 它为什么成立\n- 核心吸引力：{summary.get('core_appeal', 'uncertain')}\n- Hook 类型：{viral.get('hook_type', 'uncertain')}\n\n## 3. 可迁移骨架\n- 必须保留：{', '.join(transferable.get('must_keep', [])) or 'uncertain'}\n- 可以替换：{', '.join(transferable.get('replaceable', [])) or 'uncertain'}\n- 抽象公式：{transferable.get('abstract_pattern', 'uncertain')}\n\n## 4. 转译给 Seedance\n- 推荐模式：{seedance.get('recommended_mode', 'uncertain')}\n- 原因：{seedance.get('why', 'uncertain')}\n- 风险点：{', '.join(seedance.get('risk_points', [])) or 'uncertain'}\n"""
