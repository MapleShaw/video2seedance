"""
validation.py

Output validation module for shot_prompts.json schema compliance.
Ensures no orphaned character references, validates structure, and checks for consistency.
"""

from typing import Dict, List, Set, Tuple


class ValidationError(Exception):
    """Raised when validation fails."""
    pass


class WarningMessage:
    """Non-fatal warning that doesn't fail validation."""
    def __init__(self, message: str, severity: str = "warning"):
        self.message = message
        self.severity = severity  # "warning", "info", "debug"
    
    def __str__(self):
        return f"[{self.severity.upper()}] {self.message}"


class ValidationResult:
    """Result of a validation check."""
    def __init__(self):
        self.errors: List[str] = []
        self.warnings: List[WarningMessage] = []
        self.is_valid = True
    
    def add_error(self, message: str):
        """Add a validation error (fails validation)."""
        self.errors.append(message)
        self.is_valid = False
    
    def add_warning(self, message: str, severity: str = "warning"):
        """Add a non-fatal warning."""
        self.warnings.append(WarningMessage(message, severity))
    
    def __str__(self):
        lines = []
        if self.errors:
            lines.append(f"❌ {len(self.errors)} validation error(s):")
            for err in self.errors:
                lines.append(f"   - {err}")
        if self.warnings:
            lines.append(f"⚠️ {len(self.warnings)} warning(s):")
            for warn in self.warnings:
                lines.append(f"   - {warn}")
        if self.is_valid and not self.warnings:
            lines.append("✅ All validations passed")
        return "\n".join(lines)


def validate_shot_prompts(shot_prompts: dict) -> ValidationResult:
    """
    Validate complete shot_prompts.json structure.
    Runs all validation checks and returns aggregated result.
    """
    result = ValidationResult()
    
    if not isinstance(shot_prompts, dict):
        result.add_error("Root element must be a dict")
        return result
    
    # Check required top-level fields
    required_fields = ["metadata", "character_sheets", "shots"]
    for field in required_fields:
        if field not in shot_prompts:
            result.add_error(f"Missing required field: '{field}'")
    
    if not result.is_valid:
        return result
    
    # Validate metadata
    _validate_metadata(shot_prompts.get("metadata", {}), result)
    
    # Validate character sheets
    characters_result = _validate_character_sheets(shot_prompts.get("character_sheets", []), result)
    
    # Validate shots
    shots_result = _validate_shots(shot_prompts.get("shots", []), result)
    
    # Cross-check: validate character references
    if characters_result and shots_result:
        _validate_character_references(
            characters_result["id_to_char"],
            shots_result["referenced_char_ids"],
            result
        )
    
    # Validate variants if present
    if "variants" in shot_prompts and shot_prompts["variants"]:
        _validate_variants(shot_prompts["variants"], result)
    
    return result


def _validate_metadata(metadata: dict, result: ValidationResult):
    """Validate metadata section."""
    expected_fields = {
        "source_title": str,
        "total_duration_seconds": (int, float),
        "aspect_ratio": str,
        "seedance_skill_used": bool,
        "recommended_mode": str,
        "abstract_pattern": str,
        "risk_points": list,
        "shot_count": int,
        "character_count": int,
    }
    
    for field, expected_type in expected_fields.items():
        if field not in metadata:
            result.add_warning(f"Missing metadata field: '{field}'")
        else:
            value = metadata[field]
            if not isinstance(value, expected_type):
                result.add_error(
                    f"Metadata field '{field}' has wrong type: "
                    f"expected {expected_type}, got {type(value).__name__}"
                )


def _validate_character_sheets(character_sheets: list, result: ValidationResult) -> Dict:
    """
    Validate character_sheets array.
    Returns dict with: id_to_char (for cross-reference validation)
    """
    if not isinstance(character_sheets, list):
        result.add_error("character_sheets must be an array")
        return {}
    
    id_to_char = {}
    seen_ids = set()
    
    for idx, char in enumerate(character_sheets):
        if not isinstance(char, dict):
            result.add_error(f"character_sheets[{idx}] must be a dict, got {type(char).__name__}")
            continue
        
        # Check required fields
        required = ["id", "name", "prompt"]
        for field in required:
            if field not in char:
                result.add_error(f"character_sheets[{idx}] missing required field: '{field}'")
        
        if "id" in char:
            char_id = char["id"]
            
            # Check for duplicate IDs
            if char_id in seen_ids:
                result.add_error(
                    f"Duplicate character ID: '{char_id}' appears at indices {id_to_char[char_id]['_index']} and {idx}"
                )
            
            seen_ids.add(char_id)
            char["_index"] = idx
            id_to_char[char_id] = char
        
        # Validate prompt is non-empty
        if "prompt" in char and not char["prompt"].strip():
            result.add_error(f"character_sheets[{idx}] (id='{char.get('id')}') has empty prompt")
        
        # Validate appears_in_shots if present
        if "appears_in_shots" in char:
            if not isinstance(char["appears_in_shots"], list):
                result.add_error(
                    f"character_sheets[{idx}].appears_in_shots must be list, "
                    f"got {type(char['appears_in_shots']).__name__}"
                )
            elif not all(isinstance(x, int) for x in char["appears_in_shots"]):
                result.add_error(
                    f"character_sheets[{idx}].appears_in_shots contains non-integer values"
                )
    
    return {"id_to_char": id_to_char}


def _validate_shots(shots: list, result: ValidationResult) -> Dict:
    """
    Validate shots array.
    Returns dict with: referenced_char_ids (for cross-reference validation)
    """
    if not isinstance(shots, list):
        result.add_error("shots must be an array")
        return {"referenced_char_ids": set()}
    
    if not shots:
        result.add_warning("shots array is empty")
        return {"referenced_char_ids": set()}
    
    referenced_char_ids = set()
    seen_indices = set()
    
    for idx, shot in enumerate(shots):
        if not isinstance(shot, dict):
            result.add_error(f"shots[{idx}] must be a dict, got {type(shot).__name__}")
            continue
        
        # Check required fields
        required = ["index", "time_range", "prompt", "character_refs"]
        for field in required:
            if field not in shot:
                result.add_error(f"shots[{idx}] missing required field: '{field}'")
        
        # Validate index
        if "index" in shot:
            shot_index = shot["index"]
            if not isinstance(shot_index, int):
                result.add_error(f"shots[{idx}].index must be int, got {type(shot_index).__name__}")
            elif shot_index in seen_indices:
                result.add_error(f"Duplicate shot index: {shot_index}")
            else:
                seen_indices.add(shot_index)
        
        # Validate prompt is non-empty
        if "prompt" in shot and not shot["prompt"].strip():
            result.add_error(f"shots[{idx}] (index={shot.get('index')}) has empty prompt")
        
        # Validate character_refs
        if "character_refs" in shot:
            if not isinstance(shot["character_refs"], list):
                result.add_error(
                    f"shots[{idx}].character_refs must be list, "
                    f"got {type(shot['character_refs']).__name__}"
                )
            else:
                for char_ref in shot["character_refs"]:
                    if not isinstance(char_ref, str):
                        result.add_error(
                            f"shots[{idx}].character_refs contains non-string: {char_ref}"
                        )
                    else:
                        referenced_char_ids.add(char_ref)
        
        # Validate optional fields if present
        if "duration_seconds" in shot:
            dur = shot["duration_seconds"]
            if not isinstance(dur, (int, float)) or dur <= 0:
                result.add_warning(
                    f"shots[{idx}].duration_seconds should be positive number, got {dur}"
                )
        
        if "attention_level" in shot:
            level = shot["attention_level"]
            if not isinstance(level, int) or level < 1 or level > 5:
                result.add_warning(
                    f"shots[{idx}].attention_level should be 1-5, got {level}"
                )
        
        if "narrative_function" in shot:
            func = shot["narrative_function"]
            valid_functions = ["hook", "setup", "build", "twist", "payoff", "ending"]
            if func not in valid_functions:
                result.add_warning(
                    f"shots[{idx}].narrative_function '{func}' not in {valid_functions}"
                )
    
    # Check index continuity
    if seen_indices:
        indices = sorted(seen_indices)
        expected = list(range(1, len(indices) + 1))
        if indices != expected:
            result.add_error(
                f"Shot indices are not continuous: expected {expected}, got {indices}"
            )
    
    return {"referenced_char_ids": referenced_char_ids}


def _validate_character_references(id_to_char: Dict, referenced_char_ids: Set, result: ValidationResult):
    """Validate that all character references exist."""
    for char_ref in referenced_char_ids:
        if char_ref not in id_to_char:
            result.add_error(
                f"Orphaned character reference: '{char_ref}' referenced in shots but not defined in character_sheets"
            )
    
    # Warn about unused characters
    unused_chars = set(id_to_char.keys()) - referenced_char_ids
    for unused_id in unused_chars:
        char = id_to_char[unused_id]
        result.add_warning(
            f"Unused character: '{unused_id}' ({char.get('name', 'unnamed')}) defined but never used in shots"
        )


def _validate_variants(variants: list, result: ValidationResult):
    """Validate variants section."""
    if not isinstance(variants, list):
        result.add_warning(f"variants should be list, got {type(variants).__name__}")
        return
    
    for idx, variant in enumerate(variants):
        if not isinstance(variant, dict):
            result.add_warning(f"variants[{idx}] should be dict, got {type(variant).__name__}")
            continue
        
        if "name" not in variant:
            result.add_warning(f"variants[{idx}] missing 'name' field")


def validate_character_consistency(shot_prompts: dict) -> ValidationResult:
    """
    Check character descriptions for consistency across shots.
    Detects potential character drift issues.
    """
    result = ValidationResult()
    
    character_sheets = shot_prompts.get("character_sheets", [])
    shots = shot_prompts.get("shots", [])
    
    if not character_sheets:
        return result
    
    # Build character appearance index
    char_id_to_appearances = {}
    for shot in shots:
        for char_ref in shot.get("character_refs", []):
            if char_ref not in char_id_to_appearances:
                char_id_to_appearances[char_ref] = []
            
            summary = shot.get("subject_description_summary", "")
            if summary:
                char_id_to_appearances[char_ref].append({
                    "shot_index": shot.get("index"),
                    "summary": summary
                })
    
    # Check for consistency within each character's appearances
    for char_id, appearances in char_id_to_appearances.items():
        if len(appearances) < 2:
            continue
        
        # Simple check: look for contradictory keywords
        # e.g., "black hair" in shot 1 but "blonde hair" in shot 3
        summaries_text = " ".join(app["summary"] for app in appearances).lower()
        
        contradictions = [
            (["黑色", "black"], ["金色", "blonde", "yellow"]),
            (["长发", "long hair"], ["短发", "short hair"]),
            (["女性", "female", "girl"], ["男性", "male", "boy"]),
        ]
        
        for group_a, group_b in contradictions:
            has_a = any(term in summaries_text for term in group_a)
            has_b = any(term in summaries_text for term in group_b)
            
            if has_a and has_b:
                result.add_warning(
                    f"Character '{char_id}' shows contradictory descriptions: "
                    f"both '{group_a}' and '{group_b}' found across shots"
                )
    
    return result


def validate_style_anchor_compliance(shot_prompts: dict) -> ValidationResult:
    """
    Check that style anchor prefixes are correctly applied.
    Validates no prohibited terms appear in prompts.
    """
    result = ValidationResult()
    
    shots = shot_prompts.get("shots", [])
    character_sheets = shot_prompts.get("character_sheets", [])
    
    # Get style anchor from first shot if available
    style_anchor = None
    if shots:
        style_anchor = shots[0].get("style_anchor", "")
    
    # Check for prohibited term combinations
    prohibited_combinations = {
        "photorealistic": ["UE5", "虚幻引擎", "Unreal", "游戏引擎", "3D渲染", "CG渲染"],
        "3d-render": [],  # No universal prohibitions for 3D renders
    }
    
    def check_for_prohibited_terms(text: str, style: str) -> List[str]:
        """Return list of prohibited terms found in text."""
        if style not in prohibited_combinations:
            return []
        
        prohibited = prohibited_combinations[style]
        found = []
        text_lower = text.lower()
        
        for term in prohibited:
            term_lower = term.lower()
            if term_lower in text_lower:
                found.append(term)
        
        return found
    
    # Check shots
    for idx, shot in enumerate(shots):
        prompt = shot.get("prompt", "")
        style = shot.get("style_anchor", style_anchor or "").lower()
        
        prohibited = check_for_prohibited_terms(prompt, style)
        if prohibited:
            result.add_error(
                f"shots[{idx}] contains prohibited terms for style '{style}': {prohibited}"
            )
    
    # Check character sheets
    for idx, char in enumerate(character_sheets):
        prompt = char.get("prompt", "")
        # Characters inherit style from parent
        prohibited = check_for_prohibited_terms(prompt, style_anchor or "")
        if prohibited:
            result.add_warning(
                f"character_sheets[{idx}] (id='{char.get('id')}') contains potentially problematic terms: {prohibited}"
            )
    
    return result


def validate_7dimension_completeness(shot_prompts: dict) -> ValidationResult:
    """
    Check that character descriptions follow the 7-dimension framework:
    1. Face (脸型、眼型、眉形、鼻型、唇色、肤色、表情)
    2. Hair (发色、长度、造型、特殊状态)
    3. Headwear (类型、材质、位置、附属元素)
    4. Clothing (逐件从上到下、领口、材质、颜色、破损、层叠)
    5. Props (外观、材质、持握方式)
    6. Posture (站/坐、朝向、头部角度、肢体)
    7. Temperament/Aura (一个精确中文词组)
    """
    result = ValidationResult()
    
    character_sheets = shot_prompts.get("character_sheets", [])
    
    # Keywords to search for each dimension
    dimension_keywords = {
        "face": ["脸", "脸型", "眼", "眼型", "眉", "鼻", "唇", "肤色", "皮肤", "表情", "神态"],
        "hair": ["发色", "长发", "短发", "发型", "卷发", "直发", "头发", "发丝"],
        "headwear": ["头冠", "帽", "头饰", "头饰", "王冠", "皇冠", "链条"],
        "clothing": ["衣", "衫", "裙", "裤", "上衣", "外套", "大衣", "衣服", "服装", "衣着"],
        "props": ["手持", "拿着", "握着", "刀", "剑", "武器", "拐杖", "权杖", "枪", "弓"],
        "posture": ["站立", "站", "坐", "跪", "躺", "直视", "低头", "抬头", "侧身", "身体"],
        "temperament": ["气质", "气息", "魅力", "妖媚", "高冷", "凛然", "癫狂", "神圣", "邪恶"],
    }
    
    dimensions_present = {dim: set() for dim in dimension_keywords.keys()}
    
    for char_idx, char in enumerate(character_sheets):
        prompt = (char.get("prompt", "") + " " + char.get("name", "")).lower()
        
        # Check each dimension
        missing_dims = []
        for dim, keywords in dimension_keywords.items():
            found = any(kw in prompt for kw in keywords)
            if found:
                dimensions_present[dim].add(char.get("id", f"char_{char_idx}"))
            else:
                missing_dims.append(dim)
        
        if missing_dims:
            result.add_warning(
                f"character_sheets[{char_idx}] (id='{char.get('id')}') may be missing "
                f"7-dimension framework components: {missing_dims}. "
                f"Consider adding descriptions for: {', '.join(missing_dims)}"
            )
    
    return result


def detect_character_drift(character_sheets: list) -> ValidationResult:
    """
    Detect potential character identity drift between appearances.
    Looks for conflicting descriptions of the same character ID.
    """
    result = ValidationResult()
    
    if not character_sheets or len(character_sheets) < 2:
        return result
    
    # Build index of character descriptions
    char_id_to_descriptions = {}
    
    for idx, char in enumerate(character_sheets):
        char_id = char.get("id")
        if not char_id:
            continue
        
        prompt = char.get("prompt", "").lower()
        
        # Extract key attributes
        attributes = {
            "gender": _detect_gender(prompt),
            "apparent_age": _detect_age(prompt),
            "hair_color": _detect_hair_color(prompt),
            "hair_length": _detect_hair_length(prompt),
            "skin_tone": _detect_skin_tone(prompt),
        }
        
        if char_id not in char_id_to_descriptions:
            char_id_to_descriptions[char_id] = []
        
        char_id_to_descriptions[char_id].append({
            "index": idx,
            "attributes": attributes,
            "prompt_snippet": prompt[:100]
        })
    
    # Check for contradictions
    for char_id, descriptions in char_id_to_descriptions.items():
        if len(descriptions) < 2:
            continue
        
        # Compare first occurrence to later ones
        first_desc = descriptions[0]
        first_attrs = first_desc["attributes"]
        
        for desc in descriptions[1:]:
            attrs = desc["attributes"]
            
            # Check gender consistency
            if first_attrs["gender"] and attrs["gender"]:
                if first_attrs["gender"] != attrs["gender"]:
                    result.add_error(
                        f"Character '{char_id}' has inconsistent gender: "
                        f"character_sheets[{first_desc['index']}] → {first_attrs['gender']}, "
                        f"character_sheets[{desc['index']}] → {attrs['gender']}"
                    )
            
            # Check hair color consistency (if mentioned)
            if first_attrs["hair_color"] and attrs["hair_color"]:
                if first_attrs["hair_color"] != attrs["hair_color"]:
                    result.add_warning(
                        f"Character '{char_id}' may have different hair color: "
                        f"'{first_attrs['hair_color']}' vs '{attrs['hair_color']}'"
                    )
            
            # Check hair length consistency
            if first_attrs["hair_length"] and attrs["hair_length"]:
                if first_attrs["hair_length"] != attrs["hair_length"]:
                    result.add_warning(
                        f"Character '{char_id}' may have different hair length: "
                        f"'{first_attrs['hair_length']}' vs '{attrs['hair_length']}'"
                    )
    
    return result


def _detect_gender(text: str) -> str | None:
    """Detect gender from Chinese text."""
    if any(term in text for term in ["女性", "女人", "少女", "姑娘", "妻子", "母亲", "妹妹", "她"]):
        return "female"
    if any(term in text for term in ["男性", "男人", "少年", "小伙", "丈夫", "父亲", "哥哥", "他"]):
        return "male"
    return None


def _detect_age(text: str) -> str | None:
    """Detect apparent age from Chinese text."""
    age_keywords = {
        "child": ["幼儿", "小孩", "孩子", "婴儿"],
        "teen": ["少年", "青少年", "少女", "少男"],
        "young_adult": ["青年", "年轻", "20多", "30岁以下"],
        "adult": ["中年", "成年", "40多", "30-50"],
        "elder": ["老年", "老人", "年迈", "50岁以上"],
    }
    
    for age_group, keywords in age_keywords.items():
        if any(kw in text for kw in keywords):
            return age_group
    
    return None


def _detect_hair_color(text: str) -> str | None:
    """Detect hair color from text."""
    color_keywords = {
        "black": ["黑色", "纯黑", "漆黑"],
        "brown": ["棕色", "褐色", "栗色"],
        "blonde": ["金色", "金黄", "黄色", "亚麻"],
        "red": ["红色", "赤色"],
        "white": ["白色", "雪白"],
        "silver": ["银色", "银白"],
    }
    
    for color, keywords in color_keywords.items():
        if any(kw in text for kw in keywords):
            return color
    
    return None


def _detect_hair_length(text: str) -> str | None:
    """Detect hair length from text."""
    if any(term in text for term in ["长发", "腰长", "肩下", "及腰"]):
        return "long"
    if any(term in text for term in ["短发", "齐肩", "贴头皮", "短卷"]):
        return "short"
    if any(term in text for term in ["中长", "齐肩", "及肩"]):
        return "medium"
    return None


def _detect_skin_tone(text: str) -> str | None:
    """Detect skin tone from text."""
    if any(term in text for term in ["白皙", "苍白", "浅色"]):
        return "pale"
    if any(term in text for term in ["肤色深", "黝黑", "棕色皮肤"]):
        return "dark"
    if any(term in text for term in ["小麦色", "健康肤色", "中等肤色"]):
        return "medium"
    return None
