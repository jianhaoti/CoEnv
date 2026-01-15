"""
MCP (Model Context Protocol) Server for CoEnv.

Exposes CoEnv functionality as tools for AI agents like Claude, Cursor, Windsurf.

Available tools:
- get_status: Get current environment variable status
"""

import json
import sys
from pathlib import Path
from typing import Any, Dict

from .core.lexer import parse, get_keys
from .core.discovery import discover_env_files, aggregate_env_files, get_example_path
from .core.excludes import parse_exclude_files
from .core.metadata import MetadataStore


def get_status_tool(project_root: str = ".") -> Dict[str, Any]:
    """
    Get environment variable status.

    Returns:
        Dictionary with status information including discovered files and sources
    """
    metadata = MetadataStore(project_root)

    example_path = get_example_path(project_root)

    excluded_files = set()
    example_content = ""
    if example_path.exists():
        with open(example_path, 'r') as f:
            example_content = f.read()
        excluded_files = parse_exclude_files(example_content)

    # Discover and aggregate all .env* files
    env_files = discover_env_files(project_root, exclude_files=excluded_files)

    if not env_files:
        return {
            'success': False,
            'error': 'No .env files found'
        }

    aggregated_keys = aggregate_env_files(env_files, project_root)
    root = Path(project_root)
    discovered_files = []
    for path in env_files:
        try:
            discovered_files.append(str(path.relative_to(root)))
        except ValueError:
            discovered_files.append(path.name)

    # Parse .env.example if it exists
    example_keys = {}
    if example_content:
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
        'excluded_files': list(sorted(excluded_files)),
        'keys': keys_status,
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
