# Contributing to CoEnv

Thank you for your interest in contributing to CoEnv!

## Development Setup

1. Clone the repository:
```bash
git clone https://github.com/yourusername/coenv.git
cd coenv
```

2. Install in development mode:
```bash
pip install -e .
pip install -r requirements-dev.txt
```

3. Run tests:
```bash
pytest tests/ -v
```

4. Run the manual test suite:
```bash
python tests/manual_test.py
```

## Project Structure

```
coenv/
├── src/coenv/
│   ├── core/
│   │   ├── lexer.py        # Token-based .env parsing
│   │   ├── inference.py    # Secret/encryption detection
│   │   ├── syncer.py       # Sync logic with fuzzy matching
│   │   ├── metadata.py     # Ownership tracking
│   │   └── telemetry.py    # Anonymous usage tracking
│   ├── main.py             # CLI entry point
│   └── mcp_server.py       # MCP server for AI agents
├── tests/                   # Test suite
├── docs/                    # Documentation
└── demo/                    # Demo files
```

## Key Design Principles

1. **Lossless Parsing**: The constraint `write(parse(file)) == file` must always hold
2. **Fuzzy Matching**: Use `difflib.SequenceMatcher` with ratio > 0.8
3. **Derived Output**: Overwrite manual edits in .env.example on commit
4. **Tombstones**: Deprecated keys are blocked until explicitly undeprecated
5. **No Latency**: Telemetry must run in detached background process

## Testing

All contributions must include tests. Run the test suite:

```bash
# Run all tests
pytest tests/ -v

# Run with coverage
pytest tests/ -v --cov=coenv --cov-report=html

# Run manual integration test
python tests/manual_test.py
```

## Code Style

We use:
- `black` for code formatting
- `flake8` for linting
- Type hints where appropriate

Format your code before submitting:
```bash
black src/ tests/
flake8 src/ tests/
```

## Pull Request Process

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Make your changes with tests
4. Run the test suite
5. Commit your changes (`git commit -m 'Add amazing feature'`)
6. Push to the branch (`git push origin feature/amazing-feature`)
7. Open a Pull Request

## Reporting Issues

When reporting issues, please include:
- CoEnv version
- Python version
- Operating system
- Minimal reproducible example
- Expected vs actual behavior

## Questions?

Open an issue with the "question" label or reach out to the maintainers.
