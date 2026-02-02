#!/usr/bin/env python3
"""Fetch and print Bedrock Guardrail details using boto3."""

import json
import os
import sys

try:
    import boto3
except ImportError:
    print("Error: boto3 is required. Install with: pip install boto3", file=sys.stderr)
    sys.exit(1)


def get_guardrail_info(guardrail_id: str, guardrail_version: str = "DRAFT", region: str = None):
    region = region or os.environ.get("AWS_REGION", "us-west-2")
    client = boto3.client("bedrock", region_name=region)
    response = client.get_guardrail(
        guardrailIdentifier=guardrail_id,
        guardrailVersion=guardrail_version,
    )
    return response


def main():
    guardrail_id = os.environ.get("GUARDRAIL_ID", "87vz6bbkzfdx")
    guardrail_version = os.environ.get("GUARDRAIL_VERSION", "DRAFT")
    region = os.environ.get("AWS_REGION", "us-west-2")

    try:
        info = get_guardrail_info(guardrail_id, guardrail_version, region)
        # Convert any non-JSON-serializable types (e.g. datetime) for pretty print
        def default(o):
            import datetime
            if isinstance(o, datetime.datetime):
                return o.isoformat()
            raise TypeError(f"Object of type {type(o).__name__} is not JSON serializable")

        print(json.dumps(info, indent=2, default=default))
    except Exception as e:
        print(f"Error fetching guardrail: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
