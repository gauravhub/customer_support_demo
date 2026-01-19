#!/usr/bin/env python3
"""
MCP Gateway Authentication Module
Provides functions to authenticate with Cognito and get access tokens for MCP Gateway.
Can be used as a standalone script or imported by other modules.
"""

import json
import sys
import urllib.request
import urllib.parse
import subprocess
import os
import base64


def get_stack_output(key, stack_name=None, region=None):
    """Get a CloudFormation stack output value"""
    stack_name = stack_name or os.environ.get('STACK_NAME', 'customer-support-demo-mcp-gateway')
    region = region or os.environ.get('REGION', 'us-west-2')
    
    result = subprocess.run(
        ['aws', 'cloudformation', 'describe-stacks',
         '--stack-name', stack_name,
         '--region', region,
         '--query', f'Stacks[0].Outputs[?OutputKey==`{key}`].OutputValue',
         '--output', 'text'],
        capture_output=True,
        text=True
    )
    return result.stdout.strip()


def decode_jwt_payload(token):
    """Decode JWT token payload for debugging"""
    try:
        payload = token.split('.')[1]
        # Add padding if needed
        padding = 4 - len(payload) % 4
        if padding != 4:
            payload += '=' * padding
        decoded = base64.b64decode(payload)
        return json.loads(decoded)
    except Exception as e:
        return {'error': str(e)}


def get_cognito_credentials(stack_name=None, region=None):
    """Get Cognito credentials from CloudFormation stack outputs.
    
    Args:
        stack_name: CloudFormation stack name (defaults to env var or 'customer-support-demo-mcp-gateway')
        region: AWS region (defaults to env var or 'us-west-2')
    
    Returns:
        Dictionary with client_id, client_secret, token_endpoint, and resource_server_id
    """
    stack_name = stack_name or os.environ.get('STACK_NAME', 'customer-support-demo-mcp-gateway')
    region = region or os.environ.get('REGION', 'us-west-2')
    
    client_id = get_stack_output('CognitoUserPoolClientId', stack_name, region)
    client_secret = get_stack_output('CognitoUserPoolClientSecret', stack_name, region)
    token_endpoint = get_stack_output('CognitoTokenEndpoint', stack_name, region)
    resource_server_id = get_stack_output('CognitoResourceServerIdentifier', stack_name, region)
    
    if not resource_server_id:
        resource_server_id = stack_name
    
    return {
        'client_id': client_id,
        'client_secret': client_secret,
        'token_endpoint': token_endpoint,
        'resource_server_id': resource_server_id
    }


def get_access_token(stack_name=None, region=None, verbose=False):
    """Get access token from Cognito using client_credentials flow.
    
    Args:
        stack_name: CloudFormation stack name (defaults to env var or 'customer-support-demo-mcp-gateway')
        region: AWS region (defaults to env var or 'us-west-2')
        verbose: If True, print detailed information
    
    Returns:
        Access token string
    
    Raises:
        SystemExit: If authentication fails
    """
    stack_name = stack_name or os.environ.get('STACK_NAME', 'customer-support-demo-mcp-gateway')
    region = region or os.environ.get('REGION', 'us-west-2')
    
    if verbose:
        print("\n" + "=" * 60)
        print("Step 1: Authenticate with Cognito")
        print("=" * 60)
    
    # Get credentials from CloudFormation stack
    creds = get_cognito_credentials(stack_name, region)
    client_id = creds['client_id']
    client_secret = creds['client_secret']
    token_endpoint = creds['token_endpoint']
    resource_server_id = creds['resource_server_id']
    
    # Full scope format: {resource_server_identifier}/gateway.access
    scope = f'{resource_server_id}/gateway.access'
    
    if verbose:
        print(f"Token Endpoint: {token_endpoint}")
        print(f"Client ID: {client_id}")
        print(f"Scope: {scope}")
    
    # Use basic auth
    auth_string = f"{client_id}:{client_secret}"
    auth_bytes = auth_string.encode('utf-8')
    auth_b64 = base64.b64encode(auth_bytes).decode('utf-8')
    
    data = urllib.parse.urlencode({
        'grant_type': 'client_credentials',
        'scope': scope
    }).encode('utf-8')
    
    req = urllib.request.Request(
        token_endpoint,
        data=data,
        headers={
            'Content-Type': 'application/x-www-form-urlencoded',
            'Authorization': f'Basic {auth_b64}'
        }
    )
    
    try:
        with urllib.request.urlopen(req) as response:
            token_data = json.loads(response.read().decode('utf-8'))
            access_token = token_data['access_token']
            
            if verbose:
                print("✓ Access token obtained")
                
                # Decode and show token claims for debugging
                claims = decode_jwt_payload(access_token)
                print("\nToken Claims:")
                print(f"  Expires: {claims.get('exp', 'N/A')}")
                print(f"  Scope: {claims.get('scope', 'N/A')}")
                print(f"  Client ID: {claims.get('client_id', 'N/A')}")
            
            return access_token
    except urllib.error.HTTPError as e:
        error_body = e.read().decode('utf-8')
        error_msg = f"Error getting token (HTTP {e.code})"
        if verbose:
            print(f"✗ {error_msg}:")
            try:
                error_data = json.loads(error_body)
                print(json.dumps(error_data, indent=2))
            except:
                print(error_body)
        else:
            print(f"✗ {error_msg}: {error_body[:200]}")
        sys.exit(1)
    except Exception as e:
        error_msg = f"Error getting token: {e}"
        if verbose:
            print(f"✗ {error_msg}")
        else:
            print(f"✗ {error_msg}")
        sys.exit(1)


def main():
    """Main function when run as standalone script"""
    stack_name = os.environ.get('STACK_NAME', 'customer-support-demo-mcp-gateway')
    region = os.environ.get('REGION', 'us-west-2')
    
    print("=" * 60)
    print("MCP Gateway Authentication")
    print("=" * 60)
    print(f"Stack Name: {stack_name}")
    print(f"Region: {region}")
    print()
    
    # Get credentials
    print("Getting Cognito credentials from CloudFormation stack...")
    creds = get_cognito_credentials(stack_name, region)
    
    print("\nCognito Configuration:")
    print(f"  Client ID: {creds['client_id']}")
    print(f"  Client Secret: {creds['client_secret']}")
    print(f"  Token Endpoint: {creds['token_endpoint']}")
    print(f"  Resource Server ID: {creds['resource_server_id']}")
    print()
    
    # Get access token
    print("Authenticating with Cognito...")
    access_token = get_access_token(stack_name, region, verbose=False)
    
    print("\nAccess Token:")
    print(f"  {access_token}")
    print()
    
    # Decode token for additional info
    claims = decode_jwt_payload(access_token)
    print("Token Information:")
    print(f"  Expires: {claims.get('exp', 'N/A')}")
    print(f"  Scope: {claims.get('scope', 'N/A')}")
    print(f"  Client ID: {claims.get('client_id', 'N/A')}")
    print()
    
    print("✓ Authentication successful!")


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nInterrupted by user")
        sys.exit(130)
    except Exception as e:
        print(f"\n✗ Fatal error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
