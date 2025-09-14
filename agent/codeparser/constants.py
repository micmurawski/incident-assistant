EXTENSIONS = list(map(lambda e: f".{e}", [
    "tla",
    "js",
    "jsx",
    "ts",
    "vue",
    "tsx",
    "py",
    # Rust
    "rs",
    "go",
    # C
    "c",
    "h",
    # C++
    "cpp",
    "hpp",
    # C#
    "cs",
    # Ruby
    "rb",
    "java",
    "php",
    "swift",
    # Solidity
    "sol",
    # Kotlin
    "kt",
    "kts",
    # Elixir
    "ex",
    "exs",
    # Elisp
    "el",
    # HTML
    "html",
    "htm",
    # Markdown
    "md",
    "markdown",
    # JSON
    "json",
    # CSS
    "css",
    # SystemRDL
    "rdl",
    # OCaml
    "ml",
    "mli",
    # Lua
    "lua",
    # Scala
    "scala",
    # TOML
    "toml",
    # Zig
    "zig",
    # Elm
    "elm",
    # Embedded Template
    "ejs",
    "erb",
    # Visual Basic .NET
    "vb",
]))

FALLBACK_EXTENSION = [
    ".vb",  # Visual Basic .NET - no dedicated WASM parser
    ".scala",  # Scala - uses fallback chunking instead of Lua query workaround
    ".swift",  # Swift - uses fallback chunking due to parser instability
]
DIRS_TO_IGNORE = [
    "node_modules",
    "__pycache__",
    "env",
    "venv",
    "target/dependency",
    "build/dependencies",
    "dist",
    "out",
    "bundle",
    "vendor",
    "tmp",
    "temp",
    "deps",
    "pkg",
    "Pods",
    ".git",
    ".*",
]

MIN_BLOCK_CHARS = 50
MAX_BLOCK_CHARS = 1000
MAX_CHARS_TOLERANCE_FACTOR = 1.15
MIN_CHUNK_REMAINDER_CHARS = 200
BATCH_SEGMENT_THRESHOLD = 60
MAX_LIST_FILES_LIMIT_CODE_INDEX = 50_000

# Processing

import uuid
PARSING_CONCURRENCY = 10
BATCH_PROCESSING_CONCURRENCY = 10
MAX_FILE_SIZE = 1 * 1024 * 1024  # 1MB
MAX_PENDING_BATCHES = 20
MAX_BATCH_RETRIES = 3
QDRANT_CODE_BLOCK_NAMESPACE = uuid.UUID('6ba7b810-9dad-11d1-80b4-00c04fd430c8')
INITIAL_RETRY_DELAY_MS = 500