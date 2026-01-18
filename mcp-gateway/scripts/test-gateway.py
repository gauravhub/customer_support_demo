#!/usr/bin/env python3
"""
Comprehensive MCP Gateway Test Script
Tests authentication, tool listing, and invocation of all tools
"""

import json
import sys
import urllib.request
import urllib.parse
import subprocess
import os
import base64

REGION = os.environ.get('REGION', 'us-west-2')
STACK_NAME = os.environ.get('STACK_NAME', 'customer-support-demo-mcp-gateway')

def get_stack_output(key):
    """Get a CloudFormation stack output value"""
    result = subprocess.run(
        ['aws', 'cloudformation', 'describe-stacks',
         '--stack-name', STACK_NAME,
         '--region', REGION,
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

def get_access_token():
    """Get access token from Cognito using client_credentials flow"""
    print("\n" + "=" * 60)
    print("Step 1: Authenticate with Cognito")
    print("=" * 60)
    
    client_id = get_stack_output('CognitoUserPoolClientId')
    client_secret = get_stack_output('CognitoUserPoolClientSecret')
    token_endpoint = get_stack_output('CognitoTokenEndpoint')
    resource_server_id = get_stack_output('CognitoResourceServerIdentifier')
    
    if not resource_server_id:
        resource_server_id = STACK_NAME
    
    # Full scope format: {resource_server_identifier}/gateway.access
    scope = f'{resource_server_id}/gateway.access'
    
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
        print(f"✗ Error getting token (HTTP {e.code}):")
        try:
            error_data = json.loads(error_body)
            print(json.dumps(error_data, indent=2))
        except:
            print(error_body)
        sys.exit(1)
    except Exception as e:
        print(f"✗ Error getting token: {e}")
        sys.exit(1)

def list_tools(gateway_url, access_token):
    """Get list of available tools"""
    print("\n" + "=" * 60)
    print("Step 2: List Available Tools")
    print("=" * 60)
    
    request = {
        'jsonrpc': '2.0',
        'id': 1,
        'method': 'tools/list',
        'params': {}
    }
    
    req_data = json.dumps(request).encode('utf-8')
    req = urllib.request.Request(
        gateway_url,
        data=req_data,
        headers={
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {access_token}'
        }
    )
    
    try:
        with urllib.request.urlopen(req) as response:
            data = json.loads(response.read().decode('utf-8'))
            tools = data.get('result', {}).get('tools', [])
            
            print(f"✓ Found {len(tools)} tools")
            print()
            
            # Group tools by target
            by_target = {}
            for tool in tools:
                name = tool.get('name', 'Unknown')
                if '___' in name:
                    target = name.split('___')[0]
                else:
                    target = 'other'
                if target not in by_target:
                    by_target[target] = []
                by_target[target].append(tool)
            
            # Display grouped tools
            for target, target_tools in sorted(by_target.items()):
                print(f"  {target.upper().replace('-', ' ')} ({len(target_tools)} tools):")
                for tool in target_tools:
                    tool_name = tool.get('name', 'Unknown').split('___')[-1] if '___' in tool.get('name', '') else tool.get('name', 'Unknown')
                    print(f"    • {tool_name}")
                print()
            
            return tools
    except urllib.error.HTTPError as e:
        error_body = e.read().decode('utf-8')
        print(f"✗ Error listing tools (HTTP {e.code}):")
        try:
            error_data = json.loads(error_body)
            print(json.dumps(error_data, indent=2))
        except:
            print(error_body)
        sys.exit(1)
    except Exception as e:
        print(f"✗ Error listing tools: {e}")
        sys.exit(1)

def build_test_params(tool_name, schema):
    """Build test parameters based on tool schema"""
    params = {}
    props = schema.get('properties', {})
    required = schema.get('required', [])
    
    # Add required parameters with test values
    for req in required:
        if req in props:
            prop = props[req]
            prop_type = prop.get('type', 'string')
            
            if prop_type == 'string':
                req_lower = req.lower()
                if 'issue_key' in req_lower or 'issuekey' in req_lower:
                    params[req] = 'AS-5'
                elif 'order_no' in req_lower or 'orderno' in req_lower:
                    params[req] = 'ORD00009998'
                elif 'transaction_id' in req_lower or 'transactionid' in req_lower:
                    params[req] = 'TXN-ORD00009998-1'
                elif 'customer_id' in req_lower or 'customerid' in req_lower:
                    params[req] = 'CUST001'
                elif 'email' in req_lower:
                    params[req] = 'sarah.johnson@example.com'
                elif 'field_name' in req_lower or 'fieldname' in req_lower:
                    params[req] = 'summary'
                elif 'value' in req_lower:
                    params[req] = 'Updated test value'
                else:
                    params[req] = 'test_value'
            elif prop_type == 'boolean':
                params[req] = False
            elif prop_type in ['number', 'integer']:
                params[req] = 0
            elif prop_type == 'object':
                # Check for nested properties
                if req.lower() == 'retrievalquery':
                    params[req] = {'text': 'What is the return policy for orders?'}
                else:
                    params[req] = {}
            elif prop_type == 'array':
                params[req] = []
    
    # Special handling for Retrieve operation
    if 'Retrieve' in tool_name and 'knowledgeBaseId' not in params:
        params['knowledgeBaseId'] = 'U7KMGX9SK3'
        if 'retrievalQuery' not in params:
            params['retrievalQuery'] = {'text': 'What is the return policy for orders?'}
    
    return params

def test_tool(gateway_url, access_token, tool, request_id):
    """Test a single tool"""
    tool_name = tool.get('name', '')
    schema = tool.get('inputSchema', {})
    
    # Build parameters
    params = build_test_params(tool_name, schema)
    
    # Build request
    request = {
        'jsonrpc': '2.0',
        'id': request_id,
        'method': 'tools/call',
        'params': {
            'name': tool_name,
            'arguments': params
        }
    }
    
    # Make request
    req_data = json.dumps(request).encode('utf-8')
    req = urllib.request.Request(
        gateway_url,
        data=req_data,
        headers={
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {access_token}'
        }
    )
    
    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            response_data = json.loads(response.read().decode('utf-8'))
            
            if 'error' in response_data:
                error = response_data['error']
                return {
                    'tool': tool_name,
                    'status': 'ERROR',
                    'error_code': error.get('code', ''),
                    'error_message': error.get('message', ''),
                    'params_used': params,
                    'response': response_data
                }
            elif 'result' in response_data:
                result = response_data['result']
                # Extract meaningful info from result
                result_summary = ''
                if isinstance(result, list):
                    result_summary = f"List with {len(result)} items"
                    if len(result) > 0 and isinstance(result[0], dict):
                        result_summary += f", first item keys: {list(result[0].keys())[:5]}"
                elif isinstance(result, dict):
                    result_summary = f"Dict with keys: {list(result.keys())[:10]}"
                else:
                    result_summary = str(result)[:100]
                
                return {
                    'tool': tool_name,
                    'status': 'SUCCESS',
                    'result_type': type(result).__name__,
                    'result_summary': result_summary,
                    'params_used': params,
                    'response': response_data
                }
            else:
                return {
                    'tool': tool_name,
                    'status': 'UNKNOWN',
                    'params_used': params,
                    'response': response_data
                }
    except urllib.error.HTTPError as e:
        error_body = e.read().decode('utf-8')
        try:
            error_data = json.loads(error_body)
            error_msg = error_data.get('error', {}).get('message', error_body[:200])
        except:
            error_msg = error_body[:200]
        return {
            'tool': tool_name,
            'status': 'HTTP_ERROR',
            'http_code': e.code,
            'error_message': error_msg,
            'params_used': params
        }
    except Exception as e:
        return {
            'tool': tool_name,
            'status': 'EXCEPTION',
            'error_message': str(e)[:200],
            'params_used': params
        }

def main():
    print("=" * 60)
    print("MCP Gateway Comprehensive Test")
    print("=" * 60)
    print(f"Stack Name: {STACK_NAME}")
    print(f"Region: {REGION}")
    
    # Get configuration
    print("\nGetting configuration from CloudFormation...")
    gateway_url = get_stack_output('GatewayUrl')
    print(f"Gateway URL: {gateway_url}")
    
    # Get access token
    access_token = get_access_token()
    
    # List tools
    tools = list_tools(gateway_url, access_token)
    
    # Test each tool
    print("=" * 60)
    print("Step 3: Test All Tools")
    print("=" * 60)
    print()
    
    results = []
    for i, tool in enumerate(tools, 1):
        tool_name = tool.get('name', 'Unknown')
        print(f"[{i}/{len(tools)}] Testing: {tool_name}")
        
        result = test_tool(gateway_url, access_token, tool, i)
        results.append(result)
        
        if result['status'] == 'SUCCESS':
            print(f"  ✓ SUCCESS")
            if 'result_summary' in result:
                print(f"    Result: {result['result_summary']}")
        else:
            print(f"  ✗ {result['status']}")
            if 'error_message' in result:
                error_msg = result['error_message']
                # Truncate long errors
                if len(error_msg) > 150:
                    error_msg = error_msg[:150] + "..."
                print(f"    Error: {error_msg}")
        print()
    
    # Print summary
    print("=" * 60)
    print("Test Summary")
    print("=" * 60)
    success_count = sum(1 for r in results if r['status'] == 'SUCCESS')
    failed_count = len(results) - success_count
    
    print(f"Total tools tested: {len(results)}")
    print(f"✓ Successful: {success_count}")
    print(f"✗ Failed: {failed_count}")
    print()
    
    if failed_count > 0:
        print("Failed tools:")
        for r in results:
            if r['status'] != 'SUCCESS':
                error_msg = r.get('error_message', r.get('error_code', 'Unknown error'))
                # Truncate long errors
                if len(error_msg) > 100:
                    error_msg = error_msg[:100] + "..."
                print(f"  - {r['tool']}: {error_msg}")
        print()
    
    # Save detailed results
    results_file = '/tmp/mcp_gateway_test_results.json'
    with open(results_file, 'w') as f:
        json.dump(results, f, indent=2)
    print(f"Detailed results saved to: {results_file}")
    print()
    
    # Exit with appropriate code
    if failed_count > 0:
        print("⚠ Some tests failed. Review the results above.")
        sys.exit(1)
    else:
        print("✓ All tests passed!")
        sys.exit(0)

if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nTest interrupted by user")
        sys.exit(130)
    except Exception as e:
        print(f"\n✗ Fatal error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
