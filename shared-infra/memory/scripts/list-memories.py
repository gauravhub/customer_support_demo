#!/usr/bin/env python3
"""List all long-term memory records by discovering namespaces and saving to JSON file."""

import json
import os
import sys
import boto3
from botocore.exceptions import ClientError
from typing import List, Dict, Any

def list_records_from_namespace(client, memory_id: str, namespace: str, max_results: int = 100):
    """List all memory records from a specific namespace with pagination.
    
    Args:
        client: boto3 bedrock-agentcore client
        memory_id: AgentCore Memory ID
        namespace: Namespace to list records from
        max_results: Maximum results per page
        
    Returns:
        List of memory record summaries
    """
    all_records = []
    next_token = None
    page_count = 0
    
    while True:
        page_count += 1
        params = {
            "memoryId": memory_id,
            "namespace": namespace,
            "maxResults": max_results
        }
        
        if next_token:
            params["nextToken"] = next_token
        
        try:
            response = client.list_memory_records(**params)
            records = response.get("memoryRecordSummaries", [])
            all_records.extend(records)
            
            next_token = response.get("nextToken")
            if not next_token:
                break
                
            if page_count >= 1000:  # Safety limit
                print(f"  Warning: Reached page limit for namespace {namespace}")
                break
        except ClientError as e:
            error_code = e.response.get("Error", {}).get("Code", "")
            if error_code == "ResourceNotFoundException":
                # Namespace doesn't exist or is empty, that's okay
                break
            else:
                raise
    
    return all_records


def get_memory_strategies(client, memory_id: str):
    """Get memory strategies to understand namespace patterns.
    
    Args:
        client: boto3 bedrock-agentcore-control client
        memory_id: AgentCore Memory ID
        
    Returns:
        List of memory strategies
    """
    try:
        control_client = boto3.client("bedrock-agentcore-control", region_name=client.meta.region_name)
        response = control_client.get_memory(memoryId=memory_id)
        return response.get("strategies", [])
    except Exception as e:
        print(f"  Warning: Could not fetch memory strategies: {e}")
        return []


def discover_actor_ids_from_sessions(client, memory_id: str):
    """Try to discover actor IDs by listing sessions.
    
    Args:
        client: boto3 bedrock-agentcore client
        memory_id: AgentCore Memory ID
        
    Returns:
        Set of actor IDs found
    """
    actor_ids = set()
    try:
        # List sessions to discover actor IDs
        next_token = None
        page_count = 0
        max_pages = 10  # Limit to avoid too many calls
        
        while page_count < max_pages:
            params = {"memoryId": memory_id, "maxResults": 100}
            if next_token:
                params["nextToken"] = next_token
            
            response = client.list_sessions(**params)
            sessions = response.get("sessionSummaries", [])
            
            for session in sessions:
                actor_id = session.get("actorId")
                if actor_id:
                    actor_ids.add(actor_id)
            
            next_token = response.get("nextToken")
            if not next_token:
                break
            page_count += 1
            
    except Exception as e:
        print(f"  Warning: Could not list sessions: {e}")
    
    return actor_ids


def retrieve_all_memory_records(memory_id: str, region: str = "us-east-1", output_file: str = "memory-records.json"):
    """List all memory records by discovering namespaces from sessions and strategies.
    
    Since there's no true global namespace, we:
    1. Discover actor IDs from sessions
    2. Build namespace patterns based on memory strategies
    3. List records from each discovered namespace
    
    Args:
        memory_id: AgentCore Memory ID
        region: AWS region
        output_file: Output JSON file path
    """
    client = boto3.client("bedrock-agentcore", region_name=region)
    
    all_records = []
    namespaces_checked = []
    
    print(f"Listing all memory records from Memory ID: {memory_id}")
    print(f"Region: {region}\n")
    
    try:
        # Step 1: Try root namespace (unlikely to work, but worth trying)
        print("Step 1: Trying root namespace '/'...")
        try:
            records = list_records_from_namespace(client, memory_id, "/")
            if records:
                all_records.extend(records)
                namespaces_checked.append("/")
                print(f"  ✓ Found {len(records)} records in root namespace")
            else:
                print("  - No records in root namespace")
        except Exception as e:
            print(f"  - Root namespace not available: {type(e).__name__}")
        
        # Step 2: Discover actor IDs from sessions
        print("\nStep 2: Discovering actor IDs from sessions...")
        actor_ids = discover_actor_ids_from_sessions(client, memory_id)
        print(f"  ✓ Found {len(actor_ids)} unique actor ID(s)")
        if actor_ids:
            for actor_id in list(actor_ids)[:10]:  # Show first 10
                print(f"    - {actor_id}")
            if len(actor_ids) > 10:
                print(f"    ... and {len(actor_ids) - 10} more")
        
        # Step 3: Build namespace patterns and retrieve records
        if actor_ids:
            print(f"\nStep 3: Retrieving records from discovered namespaces...")
            
            # Common namespace patterns based on memory strategies
            namespace_patterns = [
                "/strategy/semantic/actor/{actor_id}",
                "/strategy/preferences/actor/{actor_id}",
                "/strategy/episodic/actor/{actor_id}",
            ]
            
            for actor_id in actor_ids:
                for pattern in namespace_patterns:
                    namespace = pattern.format(actor_id=actor_id)
                    try:
                        records = list_records_from_namespace(client, memory_id, namespace)
                        if records:
                            all_records.extend(records)
                            namespaces_checked.append(namespace)
                            print(f"  ✓ {namespace}: {len(records)} records")
                    except Exception as e:
                        # Silently skip namespaces that don't exist
                        pass
        
        print(f"\n{'='*60}")
        print(f"Total records collected: {len(all_records)}")
        print(f"Namespaces checked: {len(namespaces_checked)}")
        
        if not all_records:
            print("\n⚠ No records found. This could mean:")
            print("  1. No memory records exist yet")
            print("  2. No sessions exist to discover actor IDs")
            print("  3. Records are in namespaces we didn't check")
            print("  4. The memory ID is incorrect")
        
        # Save to JSON file
        output_data = {
            "memoryId": memory_id,
            "actorIdsDiscovered": list(actor_ids) if 'actor_ids' in locals() else [],
            "namespacesChecked": namespaces_checked,
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
        import traceback
        traceback.print_exc()
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
