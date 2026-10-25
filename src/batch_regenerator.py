"""
batch_regenerator.py

Support for regenerating specific batches without re-running Gemini analysis.
Useful for fixing a failed batch or tuning parameters for specific shots.

Usage:
  python batch_regenerator.py analysis.json shot_prompts.json --batch 2
  python batch_regenerator.py analysis.json shot_prompts.json --batch 2 --output output_batch2.json
"""

import argparse
import json
import sys
from pathlib import Path
from copy import deepcopy

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from shot_prompt_generator import (
    generate_shot_prompts,
    call_llm,
    build_system_prompt,
    build_user_prompt,
    load_seedance_skill,
    parse_llm_response,
)


def load_json_file(path: str) -> dict:
    """Load JSON file with error handling."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"❌ File not found: {path}")
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"❌ Invalid JSON in {path}: {e}")
        sys.exit(1)


def save_json_file(path: str, data: dict):
    """Save JSON file."""
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"✅ Saved to {path}")


def extract_batch_timeline(analysis_data: dict, batch_number: int, batch_size: int = 4) -> dict:
    """
    Extract the timeline for a specific batch.
    Batch numbering starts at 1.
    """
    timeline = analysis_data.get("timeline", [])
    
    # Calculate batch bounds
    start_idx = (batch_number - 1) * batch_size
    end_idx = min(batch_number * batch_size, len(timeline))
    
    if start_idx >= len(timeline):
        print(f"❌ Batch {batch_number} is out of range")
        print(f"   Timeline has {len(timeline)} entries, batch size is {batch_size}")
        print(f"   Max valid batch: {(len(timeline) - 1) // batch_size + 1}")
        sys.exit(1)
    
    batch_timeline = timeline[start_idx:end_idx]
    
    # Create a temporary analysis_data with just this batch
    batch_analysis = deepcopy(analysis_data)
    batch_analysis["timeline"] = batch_timeline
    
    print(f"ℹ️  Batch {batch_number} contains entries {start_idx} to {end_idx-1} ({len(batch_timeline)} entries)")
    
    return batch_analysis, start_idx, end_idx


def regenerate_batch(
    analysis_data: dict,
    batch_number: int,
    batch_size: int = 4,
    model: str = None,
    style_hint: str = None,
    image_model: str = "nanobanana",
    base_url: str = None,
    api_key: str = None,
) -> dict:
    """
    Regenerate a single batch using the LLM.
    Returns the batch results (character_sheets + shots for this batch).
    """
    print(f"\n[batch_regenerator] 生成 Batch {batch_number}...")
    
    batch_analysis, start_idx, end_idx = extract_batch_timeline(
        analysis_data, batch_number, batch_size
    )
    
    # Generate using full pipeline (which handles the batch internally)
    batch_result = generate_shot_prompts(
        batch_analysis,
        model=model,
        base_url=base_url,
        api_key=api_key,
        batch_size=batch_size,
        style_hint=style_hint,
        image_model=image_model,
    )
    
    return batch_result, start_idx, end_idx


def merge_batch_into_output(
    existing_shot_prompts: dict,
    batch_result: dict,
    batch_number: int,
    start_idx: int,
    end_idx: int,
    batch_size: int = 4,
) -> dict:
    """
    Merge regenerated batch back into existing shot_prompts.json.
    
    Strategy:
    - If batch 1: keep all new character_sheets, replace shots 1-N
    - If batch N > 1: merge new characters (avoiding duplicates), replace shots
    - Reindex all shots for continuity
    """
    result = deepcopy(existing_shot_prompts)
    
    # Merge character sheets
    existing_chars = {c["id"]: c for c in result.get("character_sheets", [])}
    new_chars = batch_result.get("character_sheets", [])
    
    chars_added = 0
    for char in new_chars:
        char_id = char["id"]
        if char_id in existing_chars:
            print(f"  ℹ️  Character '{char_id}' already exists, updating...")
            existing_chars[char_id] = char
        else:
            print(f"  ✅ Adding new character '{char_id}'")
            existing_chars[char_id] = char
            chars_added += 1
    
    result["character_sheets"] = list(existing_chars.values())
    
    # Calculate shot index range for this batch
    shot_start = (batch_number - 1) * batch_size + 1
    shot_end = shot_start + len(batch_result.get("shots", []))
    
    # Replace shots in this batch range
    existing_shots = result.get("shots", [])
    batch_shots = batch_result.get("shots", [])
    
    # Reindex batch shots to match the expected range
    for i, shot in enumerate(batch_shots):
        shot["index"] = shot_start + i
    
    # Replace shots in the range
    new_shots = (
        existing_shots[:shot_start - 1] +
        batch_shots +
        existing_shots[shot_end:]
    )
    result["shots"] = new_shots
    
    # Update metadata
    if "metadata" in result:
        result["metadata"]["character_count"] = len(existing_chars)
        result["metadata"]["shot_count"] = len(new_shots)
    
    print(f"✅ Merged batch {batch_number}:")
    print(f"   - Added {chars_added} new character(s)")
    print(f"   - Updated {len(batch_shots)} shot(s) (indices {shot_start}-{shot_end - 1})")
    
    return result


def main():
    parser = argparse.ArgumentParser(
        description="Regenerate a specific batch in shot_prompts without re-analyzing video"
    )
    parser.add_argument("analysis_json", help="Path to analysis.json (from Gemini)")
    parser.add_argument("shot_prompts_json", help="Path to existing shot_prompts.json")
    parser.add_argument(
        "--batch",
        type=int,
        required=True,
        help="Batch number to regenerate (1-indexed)"
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=4,
        help="Batch size (default: 4, must match original generation)"
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Output file (default: overwrites input shot_prompts_json)"
    )
    parser.add_argument(
        "--model",
        default=None,
        help="LLM model (default: anthropic/claude-sonnet-4.6)"
    )
    parser.add_argument(
        "--style-hint",
        default=None,
        help="Style hint to apply to regenerated batch"
    )
    parser.add_argument(
        "--image-model",
        default="nanobanana",
        choices=["nanobanana", "seedance"],
        help="Target image model"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview what would be regenerated without making changes"
    )
    
    args = parser.parse_args()
    
    # Load inputs
    print(f"📖 Loading analysis.json: {args.analysis_json}")
    analysis_data = load_json_file(args.analysis_json)
    
    print(f"📖 Loading shot_prompts.json: {args.shot_prompts_json}")
    existing_shot_prompts = load_json_file(args.shot_prompts_json)
    
    timeline = analysis_data.get("timeline", [])
    total_batches = (len(timeline) + args.batch_size - 1) // args.batch_size
    
    print(f"\nℹ️  Timeline: {len(timeline)} entries")
    print(f"ℹ️  Batch size: {args.batch_size}")
    print(f"ℹ️  Total batches: {total_batches}")
    
    if args.batch < 1 or args.batch > total_batches:
        print(f"❌ Batch {args.batch} out of range (1-{total_batches})")
        sys.exit(1)
    
    print(f"\n🔄 Regenerating batch {args.batch}...")
    
    if args.dry_run:
        batch_analysis, start_idx, end_idx = extract_batch_timeline(
            analysis_data, args.batch, args.batch_size
        )
        print(f"\n[DRY RUN] Would regenerate:")
        for i, entry in enumerate(batch_analysis["timeline"]):
            print(f"  - Timeline[{start_idx + i}]: {entry.get('visual_event', 'N/A')}")
        sys.exit(0)
    
    # Regenerate
    batch_result, start_idx, end_idx = regenerate_batch(
        analysis_data,
        args.batch,
        args.batch_size,
        model=args.model,
        style_hint=args.style_hint,
        image_model=args.image_model,
    )
    
    # Merge
    merged_result = merge_batch_into_output(
        existing_shot_prompts,
        batch_result,
        args.batch,
        start_idx,
        end_idx,
        args.batch_size,
    )
    
    # Save
    output_file = args.output or args.shot_prompts_json
    save_json_file(output_file, merged_result)
    
    print(f"\n✅ Batch regeneration complete!")
    print(f"   Total shots: {len(merged_result.get('shots', []))}")
    print(f"   Total characters: {len(merged_result.get('character_sheets', []))}")


if __name__ == "__main__":
    main()
