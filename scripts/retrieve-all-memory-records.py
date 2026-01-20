#!/usr/bin/env python3
"""Retrieve all long-term memory records globally using namespace '/' and save to JSON file."""

import json
import os
import sys
import boto3
from botocore.exceptions import ClientError
from typing import List, Dict, Any

def retrieve_all_memory_records(memory_id: str, region: str = "us-east-1", output_file: str = "memory-records.json"):
    """Retrieve all memory records globally using namespace '/' with pagination.
    
    Args:
        memory_id: AgentCore Memory ID
        region: AWS region
        output_file: Output JSON file path
    """
    client = boto3.client("bedrock-agentcore", region_name=region)
    
    all_records = []
    next_token = None
    page_count = 0
    
    print(f"Retrieving all memory records from Memory ID: {memory_id}")
    print(f"Using namespace: '/' (global)")
    print(f"Region: {region}\n")
    
    try:
        while True:
            page_count += 1
            print(f"Fetching page {page_count}...", end=" ")
            
            # Prepare request parameters
            params = {
                "memoryId": memory_id,
                "namespace": "/",
                "searchCriteria": {
                    "searchQuery": "",  # Empty query to get all records
                    "topK": 100,  # Maximum results per page
                },
                "maxResults": 100
            }
            
            if next_token:
                params["nextToken"] = next_token
            
            # Call the API
            response = client.retrieve_memory_records(**params)
            
            # Extract records
            records = response.get("memoryRecordSummaries", [])
            all_records.extend(records)
            
            print(f"Retrieved {len(records)} records (Total: {len(all_records)})")
            
            # Check for more pages
            next_token = response.get("nextToken")
            if not next_token:
                print("\nAll records retrieved!")
                break
            
            if page_count >= 1000:  # Safety limit
                print("\nWarning: Reached maximum page limit (1000 pages)")
                break
        
        # Save to JSON file
        output_data = {
            "memoryId": memory_id,
            "namespace": "/",
            "totalRecords": len(all_records),
            "records": all_records
        }
        
        with open(output_file, "w") as f:
            json.dump(output_data, f, indent=2, default=str)
        
        print(f"\n✓ Successfully saved {len(all_records)} memory records to: {output_file}")
        return all_records
        
    except ClientError as e:
        error_code = e.response.get("Error", {}).get("Code", "")
        error_message = e.response.get("Error", {}).get("Message", str(e))
        print(f"\n✗ Error: {error_code} - {error_message}")
        sys.exit(1)
    except Exception as e:
        print(f"\n✗ Unexpected error: {e}")
        sys.exit(1)


def list_memories(region: str = "us-east-1") -> List[Dict[str, Any]]:
    """List all AgentCore Memory resources.
    
    Args:
        region: AWS region
        
    Returns:
        List of memory resources
    """
    try:
        client = boto3.client("bedrock-agentcore-control", region_name=region)
        response = client.list_memories()
        return response.get("memorySummaries", [])
    except ClientError as e:
        print(f"Error listing memories: {e}")
        return []


if __name__ == "__main__":
    # Get memory ID from environment or command line
    memory_id = os.environ.get("AGENTCORE_MEMORY_ID") or (sys.argv[1] if len(sys.argv) > 1 else None)
    region = os.environ.get("AWS_REGION", "us-east-1")
    output_file = sys.argv[2] if len(sys.argv) > 2 else "memory-records.json"
    
    if not memory_id:
        print("Memory ID not provided. Listing available memories...\n")
        memories = list_memories(region)
        if memories:
            print("Available Memory Resources:")
            for mem in memories:
                print(f"  - ID: {mem.get('id')}")
                print(f"    Name: {mem.get('name')}")
                print(f"    Status: {mem.get('status')}")
                print()
            print("\nUsage: python retrieve-all-memory-records.py <memory-id> [output-file]")
            print("Or set AGENTCORE_MEMORY_ID environment variable")
        else:
            print("No memories found or unable to list memories.")
            print("\nUsage: python retrieve-all-memory-records.py <memory-id> [output-file]")
        sys.exit(1)
    
    retrieve_all_memory_records(memory_id, region, output_file)
