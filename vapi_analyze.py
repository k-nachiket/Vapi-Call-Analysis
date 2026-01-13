#!/usr/bin/env python3
"""
VAPI Call Transcript Analyzer

Analyzes transcripts from VAPI extracted calls using Google Gemini.
Adds LLM analysis results to each call object and saves the output.

Usage:
    python vapi_analyze.py vapi_call_extracted.json -o vapi_extracted_calls_analysed.json
    python vapi_analyze.py vapi_call_extracted.json  # default output
"""

import argparse
import json
import asyncio
from pathlib import Path
from typing import List, Dict, Any, Optional
from utils import get_api_key

# Default model with thinking capabilities
DEFAULT_MODEL = "gemini-3-flash-preview"

# Default prompt file
DEFAULT_PROMPT_FILE = "prompts/ANALYSIS_PROMPT_V11.txt"

# Default concurrency
DEFAULT_CONCURRENCY = 25


def load_prompt(prompt_path: Path) -> str:
    """Load the analysis prompt from a file."""
    if not prompt_path.exists():
        raise FileNotFoundError(f"Prompt file not found: {prompt_path}")
    with open(prompt_path, 'r', encoding='utf-8') as f:
        return f.read()


async def analyze_single_transcript(
    client,
    call_data: Dict[str, Any],
    prompt: str,
    model: str,
    semaphore: asyncio.Semaphore,
    index: int
) -> Dict[str, Any]:
    """
    Analyze a single transcript using Gemini.
    Returns the call_data with llm_analysis added.
    """
    from google.genai import types

    async with semaphore:
        transcript = call_data.get('transcript')
        call_id = call_data.get('id', f'index_{index}')

        # Skip if no transcript
        if not transcript or not transcript.strip():
            print(f"  [{index}] Skipping {call_id}: No transcript")
            call_data['llm_analysis'] = None
            return call_data

        try:
            print(f"  [{index}] Analyzing {call_id}...")

            # Construct the full prompt
            full_prompt = prompt + transcript

            # Generate content with thinking enabled
            config = types.GenerateContentConfig(
                temperature=0.0,
                response_mime_type="application/json",
                thinking_config=types.ThinkingConfig(
                    include_thoughts=True,
                    thinking_budget=4000
                )
            )

            # Use asyncio to run the sync call in a thread pool
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None,
                lambda: client.models.generate_content(
                    model=model,
                    contents=full_prompt,
                    config=config
                )
            )

            analysis_json = response.text.strip()

            # Clean up markdown code blocks if present
            if analysis_json.startswith("```json"):
                analysis_json = analysis_json.replace("```json", "", 1)
            if analysis_json.endswith("```"):
                analysis_json = analysis_json.rsplit("```", 1)[0]
            analysis_json = analysis_json.strip()

            # Parse JSON
            try:
                llm_result = json.loads(analysis_json)
                call_data['llm_analysis'] = llm_result
                print(f"  [{index}] Done: {call_id}")
            except json.JSONDecodeError as e:
                print(f"  [{index}] JSON parse error for {call_id}: {e}")
                call_data['llm_analysis'] = {"error": "Invalid JSON response", "raw": analysis_json[:500]}

        except Exception as e:
            print(f"  [{index}] Error analyzing {call_id}: {str(e)}")
            call_data['llm_analysis'] = {"error": str(e)}

        return call_data


async def analyze_all_calls(
    calls: List[Dict[str, Any]],
    prompt: str,
    model: str,
    concurrency: int
) -> List[Dict[str, Any]]:
    """Analyze all calls concurrently."""
    try:
        from google import genai
    except ImportError:
        print("Error: google-genai package not installed. Install with: pip install -U google-genai")
        return calls

    api_key = get_api_key("gemini")
    client = genai.Client(api_key=api_key)

    # Create semaphore for concurrency control
    semaphore = asyncio.Semaphore(concurrency)

    # Create tasks for all calls
    tasks = [
        analyze_single_transcript(client, call, prompt, model, semaphore, i)
        for i, call in enumerate(calls)
    ]

    # Run all tasks concurrently
    results = await asyncio.gather(*tasks)
    return results


def main():
    parser = argparse.ArgumentParser(
        description='Analyze VAPI call transcripts using Gemini LLM'
    )
    parser.add_argument('input', help='Input JSON file with extracted VAPI calls')
    parser.add_argument('-o', '--output', default='vapi_extracted_calls_analysed.json',
                        help='Output JSON file (default: vapi_extracted_calls_analysed.json)')
    parser.add_argument('--prompt', default=None,
                        help=f'Path to prompt file (default: {DEFAULT_PROMPT_FILE})')
    parser.add_argument('--model', default=DEFAULT_MODEL,
                        help=f'Gemini model to use (default: {DEFAULT_MODEL})')
    parser.add_argument('--concurrent', type=int, default=DEFAULT_CONCURRENCY,
                        help=f'Number of concurrent LLM calls (default: {DEFAULT_CONCURRENCY})')

    args = parser.parse_args()

    # Load input file
    input_path = Path(args.input)
    if not input_path.exists():
        print(f"Error: Input file not found: {input_path}")
        return

    with open(input_path, 'r', encoding='utf-8') as f:
        calls = json.load(f)

    print(f"Loaded {len(calls)} calls from {input_path}")

    # Load prompt
    script_dir = Path(__file__).parent.resolve()
    if args.prompt:
        prompt_path = Path(args.prompt)
        if not prompt_path.is_absolute():
            prompt_path = script_dir / prompt_path
    else:
        prompt_path = script_dir / DEFAULT_PROMPT_FILE

    try:
        prompt = load_prompt(prompt_path)
        print(f"Prompt: {prompt_path.name}")
    except FileNotFoundError as e:
        print(f"Error: {e}")
        return

    print(f"Model: {args.model}")
    print(f"Concurrency: {args.concurrent}")
    print("-" * 60)

    # Run analysis
    analyzed_calls = asyncio.run(
        analyze_all_calls(calls, prompt, args.model, args.concurrent)
    )

    # Save output
    with open(args.output, 'w', encoding='utf-8') as f:
        json.dump(analyzed_calls, f, indent=2)

    # Count results
    success = sum(1 for c in analyzed_calls if c.get('llm_analysis') and not isinstance(c.get('llm_analysis'), dict) or (isinstance(c.get('llm_analysis'), dict) and 'error' not in c.get('llm_analysis', {})))
    skipped = sum(1 for c in analyzed_calls if c.get('llm_analysis') is None)
    errors = sum(1 for c in analyzed_calls if isinstance(c.get('llm_analysis'), dict) and 'error' in c.get('llm_analysis', {}))

    print("-" * 60)
    print(f"Complete: {len(analyzed_calls)} calls processed")
    print(f"  Success: {success}")
    print(f"  Skipped (no transcript): {skipped}")
    print(f"  Errors: {errors}")
    print(f"Output saved to: {args.output}")


if __name__ == '__main__':
    main()
