#!/usr/bin/env python3
"""
Test script to update 3 fields in JIRA via MCP Gateway:
1. assignee (using gauravdhamija83@gmail.com)
2. response (custom field)
3. category (custom field)
All on issue AS-1
"""

import json
import sys
import urllib.request
import os

# Import authentication functions from mcp_auth module
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../mcp-gateway/scripts'))
from mcp_auth import get_access_token, get_stack_output

REGION = os.environ.get('REGION', 'us-west-2')
STACK_NAME = os.environ.get('STACK_NAME', 'customer-support-demo-mcp-gateway')

def call_tool(gateway_url, access_token, tool_name, arguments):
    """Call an MCP tool"""
    request = {
        'jsonrpc': '2.0',
        'id': 1,
        'method': 'tools/call',
        'params': {
            'name': tool_name,
            'arguments': arguments
        }
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
        with urllib.request.urlopen(req, timeout=30) as response:
            response_data = json.loads(response.read().decode('utf-8'))
            return response_data
    except urllib.error.HTTPError as e:
        error_body = e.read().decode('utf-8')
        try:
            error_data = json.loads(error_body)
            return {'error': error_data}
        except:
            return {'error': {'message': error_body}}
    except Exception as e:
        return {'error': {'message': str(e)}}

def main():
    print("=" * 60)
    print("Testing update_issue_field for 3 fields")
    print("=" * 60)
    print(f"Stack Name: {STACK_NAME}")
    print(f"Region: {REGION}")
    print()
    
    # Get configuration
    print("Getting configuration from CloudFormation...")
    gateway_url = get_stack_output('GatewayUrl', STACK_NAME, REGION)
    print(f"Gateway URL: {gateway_url}")
    
    # Get access token
    access_token = get_access_token(STACK_NAME, REGION, verbose=False)
    print("✓ Got access token")
    print()
    
    # MCP tool name for update_issue_field
    tool_name = "issue-management-api___update_issue_field_api_issue__issue_key__field_put"
    issue_key = "AS-1"
    
    # Test 1: Update assignee
    print("=" * 60)
    print("Test 1: Update Assignee")
    print("=" * 60)
    print(f"Issue: {issue_key}")
    print(f"Field: assignee")
    print(f"Value: gauravdhamija83@gmail.com")
    print()
    
    result = call_tool(
        gateway_url,
        access_token,
        tool_name,
        {
            "issue_key": issue_key,
            "field_name": "assignee",
            "value": "gauravdhamija83@gmail.com"
        }
    )
    
    if 'error' in result:
        print(f"✗ ERROR: {result['error']}")
    else:
        print(f"✓ SUCCESS")
        print(f"Response: {json.dumps(result.get('result', {}), indent=2)}")
    print()
    
    # Test 2: Update response
    print("=" * 60)
    print("Test 2: Update Response")
    print("=" * 60)
    print(f"Issue: {issue_key}")
    print(f"Field: response")
    print(f"Value: This is a test response from MCP Gateway")
    print()
    
    result = call_tool(
        gateway_url,
        access_token,
        tool_name,
        {
            "issue_key": issue_key,
            "field_name": "response",
            "value": "This is a test response from MCP Gateway"
        }
    )
    
    if 'error' in result:
        print(f"✗ ERROR: {result['error']}")
    else:
        print(f"✓ SUCCESS")
        print(f"Response: {json.dumps(result.get('result', {}), indent=2)}")
    print()
    
    # Test 3: Update category
    print("=" * 60)
    print("Test 3: Update Category")
    print("=" * 60)
    print(f"Issue: {issue_key}")
    print(f"Field: category")
    print(f"Value: Technical Support")
    print()
    
    result = call_tool(
        gateway_url,
        access_token,
        tool_name,
        {
            "issue_key": issue_key,
            "field_name": "category",
            "value": "Technical Support"
        }
    )
    
    if 'error' in result:
        print(f"✗ ERROR: {result['error']}")
    else:
        print(f"✓ SUCCESS")
        print(f"Response: {json.dumps(result.get('result', {}), indent=2)}")
    print()
    
    print("=" * 60)
    print("All tests completed!")
    print("=" * 60)

if __name__ == "__main__":
    main()
