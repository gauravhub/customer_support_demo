#!/usr/bin/env python3
"""Generate an AWS Console sign-in URL from credentials in environment variables.

Reads AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, and optionally AWS_SESSION_TOKEN.
If only long-term keys are set, calls STS GetSessionToken to obtain temporary
credentials, then requests a sign-in token from the AWS federation endpoint and
builds a console URL. The URL is valid for 15 minutes.

Usage:
    # With temporary credentials (e.g. from AssumeRole, SSO, or GetSessionToken):
    export AWS_ACCESS_KEY_ID=...
    export AWS_SECRET_ACCESS_KEY=...
    export AWS_SESSION_TOKEN=...
    python scripts/aws-console-url.py

    # With long-term IAM user keys (script will call GetSessionToken internally):
    export AWS_ACCESS_KEY_ID=...
    export AWS_SECRET_ACCESS_KEY=...
    python scripts/aws-console-url.py

    # Optional: open URL in browser
    python scripts/aws-console-url.py --open

    # Optional: custom destination (default: https://console.aws.amazon.com/)
    python scripts/aws-console-url.py --destination "https://console.aws.amazon.com/cloudwatch/"

Requires: boto3, requests (or use urllib for minimal deps).
"""

import argparse
import json
import os
import sys
from urllib.parse import urlencode

try:
    import boto3
    import botocore.exceptions
except ImportError:
    print("Error: boto3 is required. Install with: pip install boto3", file=sys.stderr)
    sys.exit(1)

try:
    import requests
except ImportError:
    requests = None

FEDERATION_ENDPOINT = "https://signin.aws.amazon.com/federation"
DEFAULT_DESTINATION = "https://console.aws.amazon.com/"
DEFAULT_ISSUER = "aws-console-url-script"


def get_credentials_from_env():
    """Read AWS credentials from environment. Return (access_key, secret_key, session_token or None)."""
    access_key = os.environ.get("AWS_ACCESS_KEY_ID", "").strip()
    secret_key = os.environ.get("AWS_SECRET_ACCESS_KEY", "").strip()
    session_token = os.environ.get("AWS_SESSION_TOKEN", "").strip() or None
    return access_key, secret_key, session_token


def get_temporary_credentials():
    """
    Obtain temporary credentials for federation.
    If AWS_SESSION_TOKEN is set, use env creds as-is. Otherwise call GetSessionToken.
    Returns (session_dict, from_assume_role_or_sso).
    from_assume_role_or_sso is True when creds came from env (AssumeRole/SSO/role chaining);
    for those, federation requires SessionDuration between 900-3600 to avoid 400.
    """
    access_key, secret_key, session_token = get_credentials_from_env()
    if not access_key or not secret_key:
        print(
            "Error: AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY must be set in the environment.",
            file=sys.stderr,
        )
        sys.exit(1)

    if session_token:
        # Already have temporary credentials (AssumeRole, SSO, role chaining)
        return (
            {
                "sessionId": access_key,
                "sessionKey": secret_key,
                "sessionToken": session_token,
            },
            True,
        )

    # Long-term keys: get temporary credentials via GetSessionToken
    try:
        session = boto3.Session(
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
        )
        sts = session.client("sts")
        response = sts.get_session_token(DurationSeconds=3600)
        creds = response["Credentials"]
        return (
            {
                "sessionId": creds["AccessKeyId"],
                "sessionKey": creds["SecretAccessKey"],
                "sessionToken": creds["SessionToken"],
            },
            False,
        )
    except botocore.exceptions.ClientError as e:
        print(f"Error calling GetSessionToken: {e}", file=sys.stderr)
        sys.exit(1)


def get_signin_token(session_dict, session_duration=None):
    """
    Request a sign-in token from the AWS federation endpoint.
    session_duration: optional. For AssumeRole/role chaining creds, use 900-3600 (default 3600).
    Do not pass for GetSessionToken/GetFederationToken creds.
    Uses GET per AWS docs; Session is URL-encoded in the query string.
    """
    # Compact JSON (no spaces) - federation endpoint can be strict
    session_json = json.dumps(session_dict, separators=(",", ":"))
    params = {"Action": "getSigninToken", "Session": session_json}
    if session_duration is not None:
        params["SessionDuration"] = str(session_duration)

    if requests is not None:
        resp = requests.get(FEDERATION_ENDPOINT, params=params, timeout=15)
        if not resp.ok:
            print(f"Error: federation endpoint returned {resp.status_code}", file=sys.stderr)
            if resp.text:
                print(f"Response: {resp.text[:500]}", file=sys.stderr)
            resp.raise_for_status()
        data = resp.json()
    else:
        from urllib.request import urlopen, Request
        url = FEDERATION_ENDPOINT + "?" + urlencode(params)
        req = Request(url)
        with urlopen(req, timeout=15) as r:
            data = json.loads(r.read().decode())

    token = data.get("SigninToken")
    if not token:
        print("Error: federation endpoint did not return SigninToken.", file=sys.stderr)
        sys.exit(1)
    return token


def build_console_url(signin_token, destination=None, issuer=None):
    """Build the final console login URL."""
    destination = destination or DEFAULT_DESTINATION
    issuer = issuer or DEFAULT_ISSUER
    params = {
        "Action": "login",
        "Issuer": issuer,
        "Destination": destination,
        "SigninToken": signin_token,
    }
    return FEDERATION_ENDPOINT + "?" + urlencode(params)


def open_url(url):
    """Open URL in the default browser."""
    import webbrowser
    webbrowser.open(url)


def main():
    parser = argparse.ArgumentParser(
        description="Generate AWS Console sign-in URL from environment credentials.",
        epilog="Requires AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY. Optional: AWS_SESSION_TOKEN.",
    )
    parser.add_argument(
        "--open",
        action="store_true",
        help="Open the generated URL in the default browser.",
    )
    parser.add_argument(
        "--destination",
        default=DEFAULT_DESTINATION,
        help="Console destination URL after sign-in (default: main console home).",
    )
    parser.add_argument(
        "--issuer",
        default=DEFAULT_ISSUER,
        help="Issuer name for the federation request (default: aws-console-url-script).",
    )
    parser.add_argument(
        "--session-duration",
        type=int,
        default=None,
        metavar="SECONDS",
        help="Console session duration (900–43200). Only use when credentials are from AssumeRole; do not use with GetSessionToken/GetFederationToken.",
    )
    args = parser.parse_args()

    session_dict, from_assume_role_or_sso = get_temporary_credentials()
    # Role chaining (AssumeRole/SSO) requires SessionDuration between 900-3600; omit for GetSessionToken creds
    session_duration = args.session_duration
    if from_assume_role_or_sso and session_duration is None:
        session_duration = 3600
    signin_token = get_signin_token(session_dict, session_duration=session_duration)
    url = build_console_url(signin_token, destination=args.destination, issuer=args.issuer)

    print(url)
    if args.open:
        open_url(url)


if __name__ == "__main__":
    main()
