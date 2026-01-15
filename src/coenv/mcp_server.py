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
from .core.syncer import sync_files
from .core.metadata import MetadataStore
from .main import find_env_files


def get_status_tool(project_root: str = ".") -> Dict[str, Any]:
    """
    Get environment variable status.

    Returns:
        Dictionary with status information
    """
    metadata = MetadataStore(project_root)
    env_path, example_path = find_env_files(project_root)

    if not Path(env_path).exists():
        return {
            'success': False,
            'error': '.env file not found'
        }

    # Parse .env
    with open(env_path, 'r') as f:
        env_content = f.read()

    env_keys = get_keys(parse(env_content))

    # Parse .env.example if it exists
    example_keys = {}
    if Path(example_path).exists():
        with open(example_path, 'r') as f:
            example_content = f.read()
        example_keys = get_keys(parse(example_content))

    # Build status for each key
    keys_status = []
    for key in sorted(env_keys.keys()):
        value = env_keys[key]

        # Determine repo status
        repo_status = "synced" if key in example_keys else "missing"

        # Check health
        health = "empty" if not value or value.strip() == "" else "set"

        # Get owner
        key_meta = metadata.get_key_metadata(key)
        owner = key_meta.owner if key_meta else "unknown"

        keys_status.append({
            'key': key,
            'repo_status': repo_status,
            'health': health,
            'owner': owner,
        })

    return {
        'success': True,
        'total_keys': len(env_keys),
        'synced_keys': sum(1 for k in env_keys if k in example_keys),
        'missing_keys': sum(1 for k in env_keys if k not in example_keys),
        'keys': keys_status,
    }


def trigger_sync_tool(project_root: str = ".") -> Dict[str, Any]:
    """
    Sync .env to .env.example.

    Returns:
        Dictionary with sync results
    """
    metadata = MetadataStore(project_root)
    env_path, example_path = find_env_files(project_root)

    if not Path(env_path).exists():
        return {
            'success': False,
            'error': '.env file not found'
        }

    try:
        # Perform sync
        updated_content = sync_files(env_path, example_path)

        # Write updated .env.example
        with open(example_path, 'w') as f:
            f.write(updated_content)

        # Update metadata
        with open(env_path, 'r') as f:
            env_content = f.read()

        env_keys = get_keys(parse(env_content))

        for key in env_keys:
            metadata.track_key(key)

        metadata.log_activity("sync", len(env_keys))

        return {
            'success': True,
            'keys_synced': len(env_keys),
            'message': f'Synced {len(env_keys)} keys to .env.example'
        }
    except Exception as e:
        return {
            'success': False,
            'error': str(e)
        }


def run_doctor_tool(project_root: str = ".", auto_add: bool = True) -> Dict[str, Any]:
    """
    Add missing keys from .env.example to .env.

    Args:
        project_root: Project root directory
        auto_add: If True, automatically add keys with placeholder values

    Returns:
        Dictionary with doctor results
    """
    metadata = MetadataStore(project_root)
    env_path, example_path = find_env_files(project_root)

    if not Path(example_path).exists():
        return {
            'success': False,
            'error': '.env.example file not found'
        }

    # Parse both files
    if Path(env_path).exists():
        with open(env_path, 'r') as f:
            env_content = f.read()
        env_keys = get_keys(parse(env_content))
    else:
        env_content = ""
        env_keys = {}

    with open(example_path, 'r') as f:
        example_content = f.read()

    example_keys = get_keys(parse(example_content))

    # Find missing keys
    missing_keys = set(example_keys.keys()) - set(env_keys.keys())

    if not missing_keys:
        return {
            'success': True,
            'keys_added': 0,
            'message': 'No missing keys - .env is up to date'
        }

    if not auto_add:
        return {
            'success': True,
            'keys_added': 0,
            'missing_keys': list(missing_keys),
            'message': f'Found {len(missing_keys)} missing keys (not added, auto_add=False)'
        }

    try:
        # Append missing keys to .env
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
            'keys_added': len(missing_keys),
            'added_keys': list(missing_keys),
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
                'description': 'Get current environment variable status including sync state and ownership',
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
                'description': 'Sync .env to .env.example with intelligent placeholders',
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
                'description': 'Add missing keys from .env.example to .env',
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
