#!/usr/bin/env python3
import sys
import json
import re

def main():
    try:
        input_data = json.load(sys.stdin)
    except Exception:
        sys.exit(0)  # Pass through if input isn't structured JSON

    tool_name = input_data.get("tool_name", "")
    tool_input = str(input_data.get("tool_input", ""))

    # Block direct modifications to .claude directory
    if ".claude" in tool_input:
        print("SECURITY ERROR: Modification or access to .claude directory is blocked.", file=sys.stderr)
        sys.exit(1)

    # Block network commands
    network_patterns = [r"\bcurl\b", r"\bwget\b", r"\bnetcat\b", r"\bnc\b", r"\bssh\b"]
    for pattern in network_patterns:
        if re.search(pattern, tool_input, re.IGNORECASE):
            print(f"SECURITY ERROR: Network command pattern detected and blocked: {pattern}", file=sys.stderr)
            sys.exit(1)

    # Block exposure of raw database files directly
    if re.search(r"\b(customer|db|sqlite)\b.*\b(read|cat|open)\b", tool_input, re.IGNORECASE):
        print("SECURITY ERROR: Direct inspection of raw database files is restricted.", file=sys.stderr)
        sys.exit(1)

    sys.exit(0)

if __name__ == "__main__":
    main()