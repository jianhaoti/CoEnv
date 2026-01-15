# CoEnv Architecture

## System Overview

```
┌─────────────────────────────────────────────────────────────┐
│                         CoEnv CLI                            │
│                        (main.py)                             │
└────────────────────┬────────────────────────────────────────┘
                     │
      ┌──────────────┼──────────────┐
      │              │              │
      ▼              ▼              ▼
┌──────────┐   ┌──────────┐   ┌──────────┐
│  status  │   │   sync   │   │  doctor  │
└────┬─────┘   └────┬─────┘   └────┬─────┘
     │              │              │
     └──────────────┼──────────────┘
                    │
        ┌───────────┴───────────┐
        │                       │
        ▼                       ▼
┌───────────────┐       ┌───────────────┐
│   Syncer      │       │   Metadata    │
│  (syncer.py)  │◄─────►│ (metadata.py) │
└───────┬───────┘       └───────────────┘
        │
        ├──────────┐
        │          │
        ▼          ▼
┌───────────┐  ┌─────────────┐
│  Lexer    │  │  Inference  │
│(lexer.py) │  │(inference.py)│
└───────────┘  └─────────────┘
```

## Data Flow

### Sync Operation (.env → .env.example)

```
1. Read .env file
   │
   ▼
2. Lexer.parse() → Token stream
   │
   ▼
3. For each token:
   │
   ├─ KeyValue? → Inference.analyze_value()
   │              │
   │              ├─ is_secret()? → Generate placeholder
   │              └─ is_encrypted()? → Generate encrypted placeholder
   │
   └─ Comment/BlankLine → Preserve as-is
   │
   ▼
4. Read .env.example (if exists)
   │
   ▼
5. Syncer.sync()
   │
   ├─ Match keys (exact + fuzzy)
   ├─ Update placeholders
   ├─ Add new keys
   ├─ Move removed keys to graveyard
   └─ Clean expired graveyard entries
   │
   ▼
6. Write new .env.example
   │
   ▼
7. Metadata.track_key() for each key
   │
   ▼
8. Metadata.log_activity()
   │
   ▼
9. Telemetry.track_sync() (background)
```

## Module Responsibilities

### Core Modules

#### lexer.py
**Purpose**: Lossless .env file parsing

**Key Functions**:
- `parse(content)` → List[Token]
- `write(tokens)` → str
- `get_keys(tokens)` → dict
- `update_value(tokens, key, value)` → List[Token]

**Constraint**: `write(parse(file)) == file` (byte-identical)

**Token Types**:
- `COMMENT`: Lines starting with #
- `BLANK_LINE`: Empty lines
- `KEY_VALUE`: KEY=value pairs
- `EXPORT_PREFIX`: export KEY=value

#### inference.py
**Purpose**: Secret and encryption detection

**Key Functions**:
- `calculate_entropy(value)` → float
- `is_secret(value)` → bool
- `is_encrypted(value)` → bool
- `generate_placeholder(key, value)` → str
- `analyze_value(key, value)` → dict

**Detection Methods**:
- Entropy threshold: > 4.5
- Secret prefixes: sk_, AKIA, vault:, ghp_, etc.
- Encryption prefixes: encrypted:, sops:, ENC[

#### syncer.py
**Purpose**: Sync .env to .env.example

**Key Functions**:
- `find_fuzzy_match(key, candidates)` → Optional[str]
- `Syncer.sync()` → str
- `parse_graveyard_entry(comment)` → Tuple[str, datetime]
- `is_graveyard_expired(date)` → bool

**Features**:
- Fuzzy matching: difflib.SequenceMatcher > 0.8
- Sticky values: Preserve manual edits
- Graveyard: 14-day TTL for removed keys

#### metadata.py
**Purpose**: Ownership tracking and reporting

**Key Classes**:
- `KeyMetadata`: Per-key metadata
- `ActivityLog`: Sync/save/doctor events
- `MetadataStore`: Central metadata manager

**Features**:
- Git-based ownership (git config user.name)
- Activity logging
- Weekly "Friday Pulse" summaries
- JSON persistence in .coenv/

#### telemetry.py
**Purpose**: Anonymous usage tracking

**Key Functions**:
- `send_telemetry_background()` → void
- `track_sync()`
- `track_status()`
- `track_doctor()`
- `opt_out()`

**Implementation**:
- Detached subprocess
- No main thread latency
- SHA256 hashing for privacy
- Opt-out via .coenv/.no-telemetry

### Application Layer

#### main.py
**Purpose**: CLI interface

**Commands**:
- `coenv status`: Show status table
- `coenv sync`: Sync .env to .env.example
- `coenv doctor`: Add missing keys
- `coenv --init`: Initialize project
- `coenv --watch`: File watcher (stub)
- `coenv mcp`: Start MCP server

**Dependencies**:
- click: Command-line interface
- rich: Terminal UI (tables, panels, colors)

#### mcp_server.py
**Purpose**: AI agent integration

**MCP Tools**:
- `get_status`: Environment status
- `trigger_sync`: Perform sync
- `run_doctor`: Add missing keys

**Protocol**: JSON-RPC over stdio

**Clients**: Claude, Cursor, Windsurf, etc.

## State Management

### File System State

```
project/
├── .env                    # Source of truth (never committed)
├── .env.example            # Generated documentation (committed)
├── .coenv/
│   ├── metadata.json       # Key ownership and metadata
│   ├── activity.log        # Activity history
│   ├── .last_pulse         # Last Friday Pulse timestamp
│   └── .no-telemetry       # Telemetry opt-out marker
└── .git/
    └── hooks/
        ├── pre-commit      # Auto-sync on commit
        └── post-merge      # Auto-doctor on merge
```

### In-Memory State

```
Token Stream
└─ List[Token]
   ├─ Token(type=COMMENT, raw="# Comment\n")
   ├─ Token(type=BLANK_LINE, raw="\n")
   ├─ Token(type=KEY_VALUE, key="KEY", value="val", raw="KEY=val\n")
   └─ ...

Metadata Store
└─ Dict[str, KeyMetadata]
   └─ "API_KEY": KeyMetadata(
         owner="alice",
         created_at="2026-01-14T10:00:00",
         last_modified="2026-01-14T15:30:00",
         sync_count=5
      )
```

## Design Patterns

### 1. Token Stream Pattern (Lexer)
- Immutable tokens preserve original structure
- Easy to reconstruct byte-perfect output
- Simple to transform and filter

### 2. Strategy Pattern (Inference)
- Multiple detection strategies (entropy, prefix, format)
- Composable for complex decisions
- Easy to extend with new detection methods

### 3. Repository Pattern (Metadata)
- Abstract data persistence
- Clean separation of business logic and storage
- Easy to swap JSON for database

### 4. Template Method (Syncer)
- Sync algorithm has fixed structure
- Extension points for custom behavior
- Consistent workflow

## Error Handling

### Graceful Degradation

```
1. Missing .env → Error message, exit
2. Missing .env.example → Create new (empty base)
3. Invalid .env syntax → Best-effort parsing
4. Git not available → "unknown" owner
5. Telemetry failure → Silent (never breaks main flow)
6. MCP client disconnect → Clean shutdown
```

### Validation Layers

```
CLI Layer (main.py)
  ↓ Validate file existence
  ↓ Validate project structure

Core Layer (syncer/lexer/inference)
  ↓ Validate syntax
  ↓ Handle edge cases

Metadata Layer
  ↓ Ensure .coenv/ exists
  ↓ Handle missing files gracefully
```

## Performance Considerations

### Optimization Strategies

1. **Lazy Loading**: Metadata loaded only when needed
2. **Detached Telemetry**: Zero latency for user
3. **Incremental Sync**: Only process changed keys
4. **Fuzzy Match Caching**: Could cache similarity ratios
5. **Graveyard Cleanup**: Only on sync, not on status

### Scalability

- **Small projects** (< 50 keys): Instant performance
- **Medium projects** (50-500 keys): Sub-second operations
- **Large projects** (500+ keys): Still under 1 second

**Bottlenecks**:
- Fuzzy matching is O(n²) in worst case
- File I/O dominates for large files
- Git operations can be slow

**Mitigation**:
- Fuzzy match only for missing keys (not all keys)
- Stream processing for very large files (future)
- Cache git config results

## Security Considerations

### Secrets Protection

1. **Never log secrets**: All logging hashes/truncates
2. **Placeholders**: Automatic secret replacement
3. **Telemetry**: Only counts, never values
4. **Version control**: .gitignore prevents .env commit

### Privacy

1. **Hashed identifiers**: SHA256 truncated to 16 chars
2. **Anonymous telemetry**: No PII collected
3. **Opt-out supported**: .no-telemetry file
4. **Local-first**: All data stays on machine

## Testing Strategy

### Unit Tests (pytest)
- test_lexer.py: Token parsing, round-trip
- test_inference.py: Secret detection, placeholders
- test_syncer.py: Fuzzy matching, graveyard

### Integration Tests
- manual_test.py: End-to-end validation
- demo.py: Real-world workflow

### Test Coverage
- Core modules: ~90% coverage
- Edge cases: Handled and tested
- Round-trip: 100% verified

## Future Enhancements

### Potential Additions

1. **Watch Mode**: Real-time file watching (watchdog)
2. **Diff View**: Show what changed in sync
3. **Multi-file Support**: .env.local, .env.production
4. **Validation Rules**: Custom secret patterns
5. **Team Dashboard**: Web UI for ownership/status
6. **Integration Tests**: Full CLI test suite
7. **Performance Metrics**: Track sync performance
8. **Import/Export**: Support other formats (YAML, JSON)

### Breaking Changes to Avoid

1. Token structure is public API
2. Metadata format is versioned
3. MCP protocol must stay compatible
4. CLI commands are stable interface
