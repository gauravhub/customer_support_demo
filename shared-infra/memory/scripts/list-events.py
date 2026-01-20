#!/usr/bin/env python3
"""List all raw events from AgentCore Memory and save to JSON file."""

import json
import os
import sys
import boto3
from botocore.exceptions import ClientError
from typing import List, Dict, Any, Optional

def list_sessions_for_actor(client, memory_id: str, actor_id: str, max_results: int = 100):
    """List all sessions for a specific actor.
    
    Args:
        client: boto3 bedrock-agentcore client
        memory_id: AgentCore Memory ID
        actor_id: Actor ID
        max_results: Maximum results per page
        
    Returns:
        List of session summaries
    """
    all_sessions = []
    next_token = None
    
    while True:
        params = {
            "memoryId": memory_id,
            "actorId": actor_id,
            "maxResults": max_results
        }
        
        if next_token:
            params["nextToken"] = next_token
        
        try:
            response = client.list_sessions(**params)
            sessions = response.get("sessionSummaries", [])
            all_sessions.extend(sessions)
            
            next_token = response.get("nextToken")
            if not next_token:
                break
        except ClientError as e:
            error_code = e.response.get("Error", {}).get("Code", "")
            if error_code == "ResourceNotFoundException":
                break
            else:
                raise
    
    return all_sessions


def list_events_for_session(client, memory_id: str, actor_id: str, session_id: str, 
                           include_payloads: bool = True, max_results: int = 100):
    """List all events for a specific session.
    
    Args:
        client: boto3 bedrock-agentcore client
        memory_id: AgentCore Memory ID
        actor_id: Actor ID
        session_id: Session ID
        include_payloads: Whether to include event payloads
        max_results: Maximum results per page
        
    Returns:
        List of events
    """
    all_events = []
    next_token = None
    
    while True:
        params = {
            "memoryId": memory_id,
            "actorId": actor_id,
            "sessionId": session_id,
            "includePayloads": include_payloads,
            "maxResults": max_results
        }
        
        if next_token:
            params["nextToken"] = next_token
        
        try:
            response = client.list_events(**params)
            events = response.get("events", [])
            all_events.extend(events)
            
            next_token = response.get("nextToken")
            if not next_token:
                break
        except ClientError as e:
            error_code = e.response.get("Error", {}).get("Code", "")
            if error_code == "ResourceNotFoundException":
                break
            else:
                raise
    
    return all_events


def discover_actor_ids(client, memory_id: str):
    """Try to discover actor IDs by attempting to list sessions.
    
    Note: ListSessions requires an actorId, so we can't directly list all actors.
    This function would need actor IDs to be provided or discovered another way.
    
    Args:
        client: boto3 bedrock-agentcore client
        memory_id: AgentCore Memory ID
        
    Returns:
        Set of actor IDs (empty if we can't discover them)
    """
    # Unfortunately, ListSessions requires actorId, so we can't discover actors this way
    # Users will need to provide actor IDs or we need another method
    return set()


def list_all_events(memory_id: str, actor_ids: Optional[List[str]] = None, 
                   region: str = "us-east-1", output_file: str = "events.json",
                   include_payloads: bool = True):
    """List all raw events from AgentCore Memory.
    
    Args:
        memory_id: AgentCore Memory ID
        actor_ids: Optional list of actor IDs to query. If None, will try to discover.
        region: AWS region
        output_file: Output JSON file path
        include_payloads: Whether to include event payloads in the output
    """
    client = boto3.client("bedrock-agentcore", region_name=region)
    
    all_events_data = []
    actors_processed = []
    sessions_processed = []
    
    print(f"Listing all raw events from Memory ID: {memory_id}")
    print(f"Region: {region}")
    print(f"Include payloads: {include_payloads}\n")
    
    try:
        if not actor_ids:
            print("⚠ No actor IDs provided.")
            print("Note: ListSessions requires an actorId, so we cannot automatically discover all actors.")
            print("Please provide actor IDs as command-line arguments or set ACTOR_IDS environment variable.")
            print("\nUsage: python list-events.py <memory-id> [actor-id1] [actor-id2] ... [output-file]")
            return []
        
        # Process each actor
        for actor_id in actor_ids:
            print(f"\nProcessing actor: {actor_id}")
            actors_processed.append(actor_id)
            
            # List sessions for this actor
            print(f"  Listing sessions...")
            sessions = list_sessions_for_actor(client, memory_id, actor_id)
            print(f"  ✓ Found {len(sessions)} session(s)")
            
            if not sessions:
                print(f"  - No sessions found for actor {actor_id}")
                continue
            
            # List events for each session
            for session in sessions:
                session_id = session.get("sessionId")
                if not session_id:
                    continue
                
                sessions_processed.append({
                    "actorId": actor_id,
                    "sessionId": session_id,
                    "sessionSummary": session
                })
                
                print(f"    Listing events for session {session_id[:8]}...")
                events = list_events_for_session(
                    client, memory_id, actor_id, session_id, include_payloads
                )
                print(f"      ✓ Found {len(events)} event(s)")
                
                # Add actor and session context to each event
                for event in events:
                    event_with_context = {
                        "actorId": actor_id,
                        "sessionId": session_id,
                        "event": event
                    }
                    all_events_data.append(event_with_context)
        
        print(f"\n{'='*60}")
        print(f"Summary:")
        print(f"  Actors processed: {len(actors_processed)}")
        print(f"  Sessions processed: {len(sessions_processed)}")
        print(f"  Total events: {len(all_events_data)}")
        
        # Save to JSON file
        output_data = {
            "memoryId": memory_id,
            "actorsProcessed": actors_processed,
            "sessionsProcessed": sessions_processed,
            "totalEvents": len(all_events_data),
            "events": all_events_data
        }
        
        with open(output_file, "w") as f:
            json.dump(output_data, f, indent=2, default=str)
        
        print(f"\n✓ Successfully saved {len(all_events_data)} events to: {output_file}")
        return all_events_data
        
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


if __name__ == "__main__":
    # Get memory ID from environment or command line
    memory_id = os.environ.get("AGENTCORE_MEMORY_ID") or (sys.argv[1] if len(sys.argv) > 1 else None)
    region = os.environ.get("AWS_REGION", "us-east-1")
    
    # Get actor IDs from command line or environment
    # Command line: python list-events.py <memory-id> [actor-id1] [actor-id2] ... [output-file]
    if not memory_id:
        print("Memory ID not provided.")
        print("\nUsage: python list-events.py <memory-id> [actor-id1] [actor-id2] ... [output-file]")
        print("Or set AGENTCORE_MEMORY_ID and ACTOR_IDS environment variables")
        sys.exit(1)
    
    # Parse actor IDs from command line (everything after memory_id until last arg which might be output file)
    actor_ids = None
    output_file = "events.json"
    
    if len(sys.argv) > 2:
        # Check if last argument looks like a filename (ends with .json)
        if sys.argv[-1].endswith('.json'):
            output_file = sys.argv[-1]
            actor_ids = sys.argv[2:-1] if len(sys.argv) > 3 else []
        else:
            actor_ids = sys.argv[2:]
    
    # Also check environment variable
    env_actor_ids = os.environ.get("ACTOR_IDS")
    if env_actor_ids:
        actor_ids = env_actor_ids.split(",") if not actor_ids else actor_ids
    
    # If still no actor IDs, try to get from memory records (if we have any)
    if not actor_ids:
        print("No actor IDs provided. Attempting to discover from memory records...")
        # This is a fallback - we'd need to have run list-memories.py first
        # For now, just inform the user
        print("Please provide actor IDs as arguments or set ACTOR_IDS environment variable.")
        print("\nExample:")
        print("  python list-events.py <memory-id> actor1 actor2 events.json")
        print("  export ACTOR_IDS=actor1,actor2 && python list-events.py <memory-id>")
        sys.exit(1)
    
    list_all_events(memory_id, actor_ids, region, output_file)
