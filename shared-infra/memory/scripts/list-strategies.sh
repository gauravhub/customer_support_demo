#!/bin/bash
# Script to list all strategies for an AgentCore Memory resource

set -e

REGION="${AWS_REGION:-us-west-2}"
MEMORY_ID="${1}"

if [ -z "$MEMORY_ID" ]; then
  echo "Usage: $0 <memory-id>"
  echo "Example: $0 mem-1234567890abcdef"
  exit 1
fi

echo "Listing strategies for Memory ID: $MEMORY_ID"
echo "Region: $REGION"
echo ""

cat > /tmp/list_strategies.py << 'PYTHON_SCRIPT'
import boto3
import json
import sys

region = sys.argv[1]
memory_id = sys.argv[2]

client = boto3.client('bedrock-agentcore-control', region_name=region)

try:
    response = client.get_memory(memoryId=memory_id)
    memory = response['memory']
    
    print(f"Memory: {memory['name']} ({memory['id']})")
    print(f"Status: {memory['status']}")
    print(f"Event Expiry: {memory.get('eventExpiryDuration', 'N/A')} days")
    print("")
    
    strategies = memory.get('strategies', memory.get('memoryStrategies', []))
    
    if not strategies:
        print("No strategies configured.")
    else:
        print(f"Strategies ({len(strategies)}):")
        print("=" * 60)
        
        for i, strategy in enumerate(strategies, 1):
            strategy_id = strategy.get('strategyId', strategy.get('memoryStrategyId', 'N/A'))
            strategy_type = strategy.get('type', strategy.get('memoryStrategyType', 'N/A'))
            name = strategy.get('name', 'N/A')
            status = strategy.get('status', 'N/A')
            
            print(f"\n{i}. {name}")
            print(f"   ID: {strategy_id}")
            print(f"   Type: {strategy_type}")
            print(f"   Status: {status}")
            
            namespaces = strategy.get('namespaces', [])
            if namespaces:
                print(f"   Namespaces: {', '.join(namespaces)}")
            
            # Episodic-specific reflection namespaces
            reflection_config = strategy.get('reflectionConfiguration', {})
            if reflection_config:
                reflection_namespaces = reflection_config.get('namespaces', [])
                if reflection_namespaces:
                    print(f"   Reflection Namespaces: {', '.join(reflection_namespaces)}")
            
            # Custom strategy configuration
            config = strategy.get('configuration', {})
            if config:
                print(f"   Configuration: {json.dumps(config, indent=6)}")
            
            print("-" * 60)
    
except Exception as e:
    print(f"Error: {e}")
    sys.exit(1)
PYTHON_SCRIPT

python3 /tmp/list_strategies.py "$REGION" "$MEMORY_ID"
