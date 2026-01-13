#!/usr/bin/env python3
"""
Extract specific fields from VAPI call data.

Usage:
    python vapi_extract.py vapi_all_calls.json -o vapi_call_extracted.json
    python vapi_extract.py vapi_all_calls.json  # outputs to vapi_call_extracted.json by default
"""

import argparse
import json


def extract_calls(input_file: str, output_file: str) -> int:
    """Extract specific fields from VAPI call data."""
    with open(input_file) as f:
        calls = json.load(f)

    extracted = []
    for call in calls:
        # Get duration from last message's secondsFromStart
        duration_seconds = None
        messages = call.get('messages', [])
        if messages:
            last_msg = messages[-1]
            duration_seconds = last_msg.get('secondsFromStart')

        extracted.append({
            'id': call.get('id'),
            'transcript': call.get('transcript'),
            'type': call.get('type'),
            'endedReason': call.get('endedReason'),
            'assistantId': call.get('assistantId'),
            'phoneNumberId': call.get('phoneNumberId'),
            'phoneCallProvider': call.get('phoneCallProvider'),
            'squadId': call.get('squadId'),
            'transfers': call.get('artifact', {}).get('transfers') if call.get('artifact') else None,
            'createdAt': call.get('createdAt'),
            'updatedAt': call.get('updatedAt'),
            'durationSeconds': duration_seconds,
            'orgId': call.get('orgId')
        })

    with open(output_file, 'w') as f:
        json.dump(extracted, f, indent=2)

    return len(extracted)


def main():
    parser = argparse.ArgumentParser(description='Extract specific fields from VAPI call data')
    parser.add_argument('input', help='Input JSON file with VAPI call data')
    parser.add_argument('-o', '--output', default='vapi_call_extracted.json',
                        help='Output JSON file (default: vapi_call_extracted.json)')

    args = parser.parse_args()

    count = extract_calls(args.input, args.output)
    print(f'Extracted {count} calls to {args.output}')


if __name__ == '__main__':
    main()
