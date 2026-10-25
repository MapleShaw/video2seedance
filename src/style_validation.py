"""
style_validation.py

Advanced style anchor and consistency validation.
Ensures generated prompts comply with platform-specific and realism-level rules.
"""

from typing import Dict, List, Tuple


class StyleRule:
    """Define a style rule with required/prohibited terms."""
    
    def __init__(
        self,
        realism_level: str,
        style_anchor: str,
        required_terms: List[str],
        prohibited_terms: List[str],
        recommended_terms: List[str] = None,
    ):
        self.realism_level = realism_level
        self.style_anchor = style_anchor
        self.required_terms = [t.lower() for t in required_terms]
        self.prohibited_terms = [t.lower() for t in prohibited_terms]
        self.recommended_terms = [t.lower() for t in (recommended_terms or [])]
    
    def validate(self, text: str) -> Tuple[bool, List[str], List[str]]:
        """
        Validate text against this rule.
        Returns: (is_valid, missing_required, found_prohibited)
        """
        text_lower = text.lower()
        
        # Check prohibited terms
        found_prohibited = [
            term for term in self.prohibited_terms 
            if term in text_lower
        ]
        
        # Check required terms (at least one must be present)
        if self.required_terms:
            has_required = any(term in text_lower for term in self.required_terms)
            missing_required = self.required_terms if not has_required else []
        else:
            missing_required = []
        
        is_valid = len(found_prohibited) == 0
        
        return is_valid, missing_required, found_prohibited


# Define comprehensive style rules
STYLE_RULES = {
    "photorealistic": StyleRule(
        realism_level="photorealistic",
        style_anchor="写实真人",
        required_terms=[
            "电影级真人实拍", "cinematic live-action", "写实摄影", 
            "自然皮肤质感", "真人实拍"
        ],
        prohibited_terms=[
            "UE5", "虚幻引擎", "Unreal", "unreal engine",
            "游戏引擎", "game engine", "3D渲染", "CG渲染",
            "超写实CG", "高端CG", "3D角色"
        ],
        recommended_terms=[
            "自然光影", "毛孔细节", "写实", "摄影",
            "真实", "natural"
        ]
    ),
    
    "semi-realistic": StyleRule(
        realism_level="semi-realistic",
        style_anchor="半写实",
        required_terms=[
            "电影级", "写实", "摄影", "真人"
        ],
        prohibited_terms=[
            "UE5", "虚幻引擎", "游戏引擎", "CG渲染"
        ],
        recommended_terms=[
            "艺术质感", "电影风格", "精细光影"
        ]
    ),
    
    "3d-render": StyleRule(
        realism_level="3d-render",
        style_anchor="3D渲染",
        required_terms=[
            "3D渲染", "3D模型", "渲染", "CG", "UE5", "虚幻引擎"
        ],
        prohibited_terms=[],  # No universal prohibitions for 3D
        recommended_terms=[
            "超写实", "次表面散射", "光线追踪", "PBR"
        ]
    ),
    
    "anime": StyleRule(
        realism_level="anime",
        style_anchor="动画",
        required_terms=[
            "动画", "二次元", "卡通", "anime", "illustration"
        ],
        prohibited_terms=[
            "真人", "真实", "photorealistic", "live-action",
            "电影级", "写实", "摄影"
        ],
        recommended_terms=[
            "赛璐璃", "手绘风格", "原画", "角色设定图"
        ]
    ),
    
    "stylized": StyleRule(
        realism_level="stylized",
        style_anchor="艺术风格",
        required_terms=[
            "艺术", "风格化", "stylized", "artistic"
        ],
        prohibited_terms=[],
        recommended_terms=[
            "绘画风格", "油画", "素描", "水彩"
        ]
    ),
}


class StyleValidationResult:
    """Result of style validation."""
    
    def __init__(self):
        self.is_valid = True
        self.errors: List[Dict] = []
        self.warnings: List[Dict] = []
    
    def add_error(self, message: str, prompt_type: str, index: int = None):
        """Add validation error."""
        self.is_valid = False
        self.errors.append({
            "message": message,
            "type": prompt_type,
            "index": index
        })
    
    def add_warning(self, message: str, prompt_type: str, index: int = None):
        """Add validation warning."""
        self.warnings.append({
            "message": message,
            "type": prompt_type,
            "index": index
        })
    
    def __str__(self):
        lines = []
        if self.errors:
            lines.append(f"❌ {len(self.errors)} style validation error(s):")
            for err in self.errors:
                if err["index"] is not None:
                    lines.append(f"   [{err['type']}#{err['index']}] {err['message']}")
                else:
                    lines.append(f"   [{err['type']}] {err['message']}")
        if self.warnings:
            lines.append(f"⚠️ {len(self.warnings)} style warning(s):")
            for warn in self.warnings:
                if warn["index"] is not None:
                    lines.append(f"   [{warn['type']}#{warn['index']}] {warn['message']}")
                else:
                    lines.append(f"   [{warn['type']}] {warn['message']}")
        if self.is_valid and not self.warnings:
            lines.append("✅ Style validation passed")
        return "\n".join(lines)


def validate_style_anchor_prefix(shot_prompts: dict, realism_level: str = None) -> StyleValidationResult:
    """
    Validate that style anchors are correctly applied.
    Detects misaligned realism_level + style_anchor combinations.
    """
    result = StyleValidationResult()
    
    # Try to infer realism_level if not provided
    if not realism_level:
        realism_level = _infer_realism_level(shot_prompts)
    
    if not realism_level or realism_level not in STYLE_RULES:
        result.add_warning(
            f"Cannot determine realism_level (got: {realism_level}), skipping style validation",
            "metadata"
        )
        return result
    
    rule = STYLE_RULES[realism_level]
    
    # Validate shots
    shots = shot_prompts.get("shots", [])
    for idx, shot in enumerate(shots):
        prompt = shot.get("prompt", "")
        if not prompt.strip():
            result.add_error("Empty shot prompt", "shot", idx)
            continue
        
        # Check required terms
        has_required = any(term in prompt.lower() for term in rule.required_terms)
        if not has_required:
            result.add_error(
                f"Shot prompt missing required style terms. "
                f"Expected one of: {', '.join(rule.required_terms[:3])}...",
                "shot",
                idx
            )
        
        # Check prohibited terms
        found_prohibited = [
            term for term in rule.prohibited_terms
            if term.lower() in prompt.lower()
        ]
        if found_prohibited:
            result.add_error(
                f"Shot contains prohibited terms for {realism_level}: {found_prohibited}",
                "shot",
                idx
            )
        
        # Check for recommended terms (warning only)
        has_recommended = any(term in prompt.lower() for term in rule.recommended_terms)
        if not has_recommended and rule.recommended_terms:
            result.add_warning(
                f"Shot could benefit from recommended terms: {rule.recommended_terms[:2]}",
                "shot",
                idx
            )
    
    # Validate character sheets
    characters = shot_prompts.get("character_sheets", [])
    for idx, char in enumerate(characters):
        prompt = char.get("prompt", "")
        if not prompt.strip():
            result.add_error("Empty character prompt", "character", idx)
            continue
        
        # Check for prohibited terms (more lenient for characters)
        found_prohibited = [
            term for term in rule.prohibited_terms
            if term.lower() in prompt.lower()
        ]
        if found_prohibited:
            result.add_warning(
                f"Character contains terms that may conflict with {realism_level}: {found_prohibited}",
                "character",
                idx
            )
    
    return result


def validate_platform_compliance(shot_prompts: dict, platform: str = "seedance") -> StyleValidationResult:
    """
    Validate that prompts comply with platform-specific rules.
    """
    result = StyleValidationResult()
    
    if platform == "seedance":
        # Seedance-specific rules
        # 1. No realistic faces (platform blocks as photorealistic)
        # 2. Must use "角色设定图" not "人物肖像"
        # 3. Quality terms at END
        
        characters = shot_prompts.get("character_sheets", [])
        for idx, char in enumerate(characters):
            prompt = char.get("prompt", "").lower()
            
            # Check for Seedance compliance
            if "人物肖像" in prompt or "写实人像" in prompt:
                result.add_warning(
                    "Character uses prohibited term '人物肖像' - Seedance blocks realistic faces. "
                    "Use '角色设定图' instead",
                    "character",
                    idx
                )
            
            if "真人写实" in prompt and "角色设定图" not in prompt:
                result.add_warning(
                    "Character mixes realistic description without '角色设定图' wrapper",
                    "character",
                    idx
                )
    
    elif platform == "nanobanana":
        # NanoBanana-specific rules
        # 1. All Chinese prompts
        # 2. No Midjourney/SD syntax
        
        def has_non_chinese_ratio(text: str) -> float:
            """Return ratio of non-Chinese characters."""
            import re
            chinese = len(re.findall(r'[\u4e00-\u9fff]', text))
            total = len([c for c in text if not c.isspace()])
            if total == 0:
                return 0
            return (total - chinese) / total
        
        all_prompts = []
        for char in shot_prompts.get("character_sheets", []):
            all_prompts.append(("character", char.get("prompt", "")))
        for idx, shot in enumerate(shot_prompts.get("shots", [])):
            all_prompts.append(("shot", shot.get("prompt", "")))
        
        for prompt_type, prompt in all_prompts:
            non_chinese_ratio = has_non_chinese_ratio(prompt)
            if non_chinese_ratio > 0.3:  # More than 30% non-Chinese
                result.add_warning(
                    f"{prompt_type.capitalize()} has {non_chinese_ratio*100:.1f}% non-Chinese content. "
                    f"NanoBanana prefers all-Chinese prompts",
                    prompt_type
                )
            
            # Check for MJ/SD syntax
            if any(term in prompt for term in ["--ar", "--v", "--style", "--niji"]):
                result.add_error(
                    f"{prompt_type.capitalize()} contains Midjourney syntax (--ar, --v, etc). "
                    f"NanoBanana is Google Gen-AI, not compatible",
                    prompt_type
                )
            
            if any(term in prompt for term in ["masterpiece", "best quality", "1girl", "1boy"]):
                result.add_warning(
                    f"{prompt_type.capitalize()} contains Stable Diffusion syntax. "
                    f"NanoBanana doesn't respond to SD keywords",
                    prompt_type
                )
    
    return result


def _infer_realism_level(shot_prompts: dict) -> str | None:
    """Try to infer realism_level from metadata or shot descriptions."""
    # Check metadata first
    metadata = shot_prompts.get("metadata", {})
    if "realism_level" in metadata:
        return metadata["realism_level"]
    
    # Try to infer from style_anchor in shots
    shots = shot_prompts.get("shots", [])
    if shots:
        style_anchor = shots[0].get("style_anchor", "").lower()
        if "photorealistic" in style_anchor or "写实" in style_anchor:
            return "photorealistic"
        elif "3d" in style_anchor or "渲染" in style_anchor:
            return "3d-render"
        elif "anime" in style_anchor or "动画" in style_anchor:
            return "anime"
    
    return None


def compare_style_consistency(shot_prompts: dict) -> Dict:
    """
    Analyze style consistency across all shots.
    Returns a report with statistics and potential issues.
    """
    report = {
        "total_shots": 0,
        "style_anchors": {},
        "consistency_score": 0.0,
        "issues": [],
    }
    
    shots = shot_prompts.get("shots", [])
    report["total_shots"] = len(shots)
    
    # Collect all style anchors
    anchors = {}
    for shot in shots:
        anchor = shot.get("style_anchor", "unknown")
        anchors[anchor] = anchors.get(anchor, 0) + 1
    
    report["style_anchors"] = anchors
    
    # Calculate consistency score (how uniform is the style)
    if len(anchors) == 1:
        report["consistency_score"] = 1.0
    else:
        # Score = 1 - (variety / max_variety)
        variety = len(anchors)
        max_variety = len(shots)
        report["consistency_score"] = 1.0 - (variety / max_variety)
    
    # Detect inconsistent shots
    if len(anchors) > 1:
        primary_anchor = max(anchors, key=anchors.get)
        for idx, shot in enumerate(shots):
            if shot.get("style_anchor") != primary_anchor:
                report["issues"].append({
                    "shot": idx + 1,
                    "message": f"Style anchor differs from primary: "
                              f"'{shot.get('style_anchor')}' vs '{primary_anchor}'"
                })
    
    return report
