"""
test_validation.py

Unit tests for validation module.
Tests schema validation, character consistency, and style anchor compliance.
"""

import sys
import unittest
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from validation import (
    validate_shot_prompts,
    validate_character_consistency,
    validate_style_anchor_compliance,
    ValidationError,
    ValidationResult,
)


class TestValidateShotPrompts(unittest.TestCase):
    """Test schema validation."""
    
    def test_valid_minimal_structure(self):
        """Test that minimal valid structure passes."""
        data = {
            "metadata": {"shot_count": 1},
            "character_sheets": [],
            "shots": [
                {
                    "index": 1,
                    "time_range": "0s-5s",
                    "prompt": "Some prompt",
                    "character_refs": []
                }
            ]
        }
        result = validate_shot_prompts(data)
        self.assertTrue(result.is_valid)
    
    def test_missing_required_top_level_fields(self):
        """Test that missing top-level fields fail validation."""
        data = {
            "metadata": {},
            "character_sheets": []
            # missing shots
        }
        result = validate_shot_prompts(data)
        self.assertFalse(result.is_valid)
        self.assertTrue(any("shots" in err for err in result.errors))
    
    def test_orphaned_character_reference(self):
        """Test detection of character referenced but not defined."""
        data = {
            "metadata": {"shot_count": 1},
            "character_sheets": [],
            "shots": [
                {
                    "index": 1,
                    "time_range": "0s-5s",
                    "prompt": "Prompt",
                    "character_refs": ["char_A"]  # Not defined!
                }
            ]
        }
        result = validate_shot_prompts(data)
        self.assertFalse(result.is_valid)
        self.assertTrue(any("Orphaned" in err for err in result.errors))
    
    def test_duplicate_character_ids(self):
        """Test detection of duplicate character IDs."""
        data = {
            "metadata": {"shot_count": 1},
            "character_sheets": [
                {"id": "char_A", "name": "Character A", "prompt": "Prompt 1"},
                {"id": "char_A", "name": "Character A", "prompt": "Prompt 2"},  # Duplicate!
            ],
            "shots": [
                {
                    "index": 1,
                    "time_range": "0s-5s",
                    "prompt": "Prompt",
                    "character_refs": ["char_A"]
                }
            ]
        }
        result = validate_shot_prompts(data)
        self.assertFalse(result.is_valid)
        self.assertTrue(any("Duplicate character ID" in err for err in result.errors))
    
    def test_empty_character_prompt(self):
        """Test detection of empty character prompts."""
        data = {
            "metadata": {"shot_count": 1},
            "character_sheets": [
                {"id": "char_A", "name": "Character A", "prompt": ""}  # Empty!
            ],
            "shots": [
                {
                    "index": 1,
                    "time_range": "0s-5s",
                    "prompt": "Prompt",
                    "character_refs": ["char_A"]
                }
            ]
        }
        result = validate_shot_prompts(data)
        self.assertFalse(result.is_valid)
        self.assertTrue(any("empty prompt" in err for err in result.errors))
    
    def test_non_continuous_shot_indices(self):
        """Test detection of non-continuous shot indices."""
        data = {
            "metadata": {"shot_count": 2},
            "character_sheets": [],
            "shots": [
                {
                    "index": 1,
                    "time_range": "0s-5s",
                    "prompt": "Prompt 1",
                    "character_refs": []
                },
                {
                    "index": 3,  # Should be 2!
                    "time_range": "5s-10s",
                    "prompt": "Prompt 2",
                    "character_refs": []
                }
            ]
        }
        result = validate_shot_prompts(data)
        self.assertFalse(result.is_valid)
        self.assertTrue(any("not continuous" in err for err in result.errors))


if __name__ == "__main__":
    unittest.main()
