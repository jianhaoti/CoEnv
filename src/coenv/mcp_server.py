"""
MCP (Model Context Protocol) Server for CoEnv.

Exposes CoEnv functionality as tools for AI agents like Claude, Cursor, Windsurf.

Available tools:
- get_status: Get current environment variable status
- trigger_sync: Sync .env to .env.example
- run_doctor: Add missing keys from .env.example to .env
"""

import json
import sys
from pathlib import Path
from typing import Any, Dict

from .core.lexer import parse, get_keys
from .core.syncer import sync_files, sync_aggregated
from .core.discovery import discover_env_files, aggregate_env_files, get_example_path
from .core.metadata import MetadataStore


def get_status_tool(project_root: str = ".") -> Dict[str, Any]:
    """
    Get environment variable status.

    Returns:
        Dictionary with status information including discovered files and sources
    """
    metadata = MetadataStore(project_root)

    # Discover and aggregate all .env* files
    env_files = discover_env_files(project_root)
    example_path = get_example_path(project_root)

    if not env_files:
        return {
            'success': False,
            'error': 'No .env files found'
        }

    aggregated_keys = aggregate_env_files(env_files, project_root)
    discovered_files = [f.name for f in env_files]

    # Parse .env.example if it exists
    example_keys = {}
    if example_path.exists():
        with open(example_path, 'r') as f:
            example_content = f.read()
        example_keys = get_keys(parse(example_content))

    # Build status for each key
    keys_status = []
    for key in sorted(aggregated_keys.keys()):
        agg_key = aggregated_keys[key]
        value = agg_key.value

        # Determine repo status
        repo_status = "synced" if key in example_keys else "missing"

        # Check health
        health = "empty" if not value or value.strip() == "" else "set"

        # Get owner
        key_meta = metadata.get_key_metadata(key)
        owner = key_meta.owner if key_meta else "unknown"

        keys_status.append({
            'key': key,
            'source': agg_key.source,
            'all_sources': agg_key.all_sources,
            'repo_status': repo_status,
            'health': health,
            'owner': owner,
        })

    return {
        'success': True,
        'discovered_files': discovered_files,
        'total_keys': len(aggregated_keys),
        'synced_keys': sum(1 for k in aggregated_keys if k in example_keys),
        'missing_keys': sum(1 for k in aggregated_keys if k not in example_keys),
        'keys': keys_status,
    }


def trigger_sync_tool(project_root: str = ".") -> Dict[str, Any]:
    """
    Sync all .env* files to .env.example.

    Returns:
        Dictionary with sync results including discovered files
    """
    metadata = MetadataStore(project_root)

    # Discover and aggregate all .env* files
    env_files = discover_env_files(project_root)
    example_path = get_example_path(project_root)

    if not env_files:
        return {
            'success': False,
            'error': 'No .env files found'
        }

    try:
        aggregated_keys = aggregate_env_files(env_files, project_root)
        discovered_files = [f.name for f in env_files]

        # Perform aggregated sync
        updated_content, syncer = sync_aggregated(aggregated_keys, str(example_path))

        # Write updated .env.example
        with open(example_path, 'w') as f:
            f.write(updated_content)

        # Update metadata with source tracking
        for key, agg_key in aggregated_keys.items():
            metadata.track_key(key, source=agg_key.source)

        metadata.log_activity("sync", len(aggregated_keys))

        return {
            'success': True,
            'discovered_files': discovered_files,
            'keys_synced': len(aggregated_keys),
            'message': f'Synced {len(aggregated_keys)} keys from {len(discovered_files)} file(s) to .env.example'
        }
    except Exception as e:
        return {
            'success': False,
            'error': str(e)
        }


def run_doctor_tool(project_root: str = ".", auto_add: bool = True) -> Dict[str, Any]:
    """
    Add missing keys from .env.example to .env.

    Compares .env.example against all discovered .env* files and appends
    any missing keys to the base .env file.

    Args:
        project_root: Project root directory
        auto_add: If True, automatically add keys with placeholder values

    Returns:
        Dictionary with doctor results
    """
    metadata = MetadataStore(project_root)

    # Discover and aggregate all .env* files
    env_files = discover_env_files(project_root)
    example_path = get_example_path(project_root)

    if not example_path.exists():
        return {
            'success': False,
            'error': '.env.example file not found'
        }

    # Get aggregated keys from all discovered files
    aggregated_keys = aggregate_env_files(env_files, project_root) if env_files else {}
    discovered_files = [f.name for f in env_files]

    # Get the base .env file path for appending missing keys
    env_path = Path(project_root) / ".env"

    # Read existing .env content if it exists
    if env_path.exists():
        with open(env_path, 'r') as f:
            env_content = f.read()
    else:
        env_content = ""

    # Parse .env.example
    with open(example_path, 'r') as f:
        example_content = f.read()

    example_keys = get_keys(parse(example_content))

    # Find missing keys (in .env.example but not in any discovered .env* file)
    missing_keys = set(example_keys.keys()) - set(aggregated_keys.keys())

    if not missing_keys:
        return {
            'success': True,
            'discovered_files': discovered_files,
            'keys_added': 0,
            'message': 'No missing keys - environment is up to date'
        }

    if not auto_add:
        return {
            'success': True,
            'discovered_files': discovered_files,
            'keys_added': 0,
            'missing_keys': list(missing_keys),
            'message': f'Found {len(missing_keys)} missing keys (not added, auto_add=False)'
        }

    try:
        # Append missing keys to base .env file
        with open(env_path, 'a') as f:
            if env_content and not env_content.endswith('\n'):
                f.write('\n')

            f.write('\n# Added by coenv doctor\n')

            for key in sorted(missing_keys):
                placeholder_value = example_keys[key]
                f.write(f"{key}={placeholder_value}\n")

        metadata.log_activity("doctor", len(missing_keys))

        return {
            'success': True,
            'discovered_files': discovered_files,
            'keys_added': len(missing_keys),
            'added_keys': list(sorted(missing_keys)),
            'message': f'Added {len(missing_keys)} keys to .env'
        }
    except Exception as e:
        return {
            'success': False,
            'error': str(e)
        }


# MCP Server Implementation
def handle_tool_call(tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
    """
    Handle a tool call from MCP client.

    Args:
        tool_name: Name of the tool to call
        arguments: Tool arguments

    Returns:
        Tool result dictionary
    """
    project_root = arguments.get('project_root', '.')

    if tool_name == 'get_status':
        return get_status_tool(project_root)
    elif tool_name == 'trigger_sync':
        return trigger_sync_tool(project_root)
    elif tool_name == 'run_doctor':
        auto_add = arguments.get('auto_add', True)
        return run_doctor_tool(project_root, auto_add)
    else:
        return {
            'success': False,
            'error': f'Unknown tool: {tool_name}'
        }


def run_server():
    """
    Run the MCP server.

    Reads JSON-RPC messages from stdin and writes responses to stdout.
    """
    # Server metadata
    server_info = {
        'name': 'coenv',
        'version': '0.1.0',
        'tools': [
            {
                'name': 'get_status',
                'description': 'Get environment variable status from all .env* files, including source tracking and sync state',
                'parameters': {
                    'type': 'object',
                    'properties': {
                        'project_root': {
                            'type': 'string',
                            'description': 'Project root directory (default: current directory)',
                            'default': '.'
                        }
                    }
                }
            },
            {
                'name': 'trigger_sync',
                'description': 'Sync all .env* files to .env.example with priority merging (.env.local > .env.[mode] > .env)',
                'parameters': {
                    'type': 'object',
                    'properties': {
                        'project_root': {
                            'type': 'string',
                            'description': 'Project root directory (default: current directory)',
                            'default': '.'
                        }
                    }
                }
            },
            {
                'name': 'run_doctor',
                'description': 'Add missing keys from .env.example that are not in any .env* file',
                'parameters': {
                    'type': 'object',
                    'properties': {
                        'project_root': {
                            'type': 'string',
                            'description': 'Project root directory (default: current directory)',
                            'default': '.'
                        },
                        'auto_add': {
                            'type': 'boolean',
                            'description': 'Automatically add missing keys (default: true)',
                            'default': True
                        }
                    }
                }
            }
        ]
    }

    # Simple stdio-based JSON-RPC server
    print(json.dumps(server_info), file=sys.stderr)
    sys.stderr.flush()

    try:
        for line in sys.stdin:
            if not line.strip():
                continue

            try:
                request = json.loads(line)

                if request.get('method') == 'tools/call':
                    params = request.get('params', {})
                    tool_name = params.get('name')
                    arguments = params.get('arguments', {})

                    result = handle_tool_call(tool_name, arguments)

                    response = {
                        'jsonrpc': '2.0',
                        'id': request.get('id'),
                        'result': result
                    }

                    print(json.dumps(response))
                    sys.stdout.flush()

            except json.JSONDecodeError:
                continue

    except KeyboardInterrupt:
        pass


if __name__ == '__main__':
    run_server()
