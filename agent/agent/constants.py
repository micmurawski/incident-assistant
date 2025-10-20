import uuid

EXTENSIONS = list(
    map(
        lambda e: f".{e}",
        [
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
        ],
    )
)

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
DEFAULT_MIN_COMPONENT_LINES_VALUE = 4

MIN_BLOCK_CHARS = 50
MAX_BLOCK_CHARS = 1000
MAX_CHARS_TOLERANCE_FACTOR = 1.15
MIN_CHUNK_REMAINDER_CHARS = 200
BATCH_SEGMENT_THRESHOLD = 60
MAX_LIST_FILES_LIMIT_CODE_INDEX = 50_000

# Processing


PARSING_CONCURRENCY = 10
BATCH_PROCESSING_CONCURRENCY = 10
MAX_FILE_SIZE = 1 * 1024 * 1024  # 1MB
MAX_PENDING_BATCHES = 20
MAX_BATCH_RETRIES = 3

QDRANT_CODE_BLOCK_NAMESPACE = uuid.UUID("6ba7b810-9dad-11d1-80b4-00c04fd430c8")
QDRANT_DEFAULT_URL = "http://localhost:6333"
INITIAL_RETRY_DELAY_MS = 500
MAX_ITEM_TOKENS = 8191

CODEBASE_INDEX_DEFAULTS = dict(
    MIN_SEARCH_RESULTS=10,
    MAX_SEARCH_RESULTS=200,
    DEFAULT_SEARCH_RESULTS=50,
    SEARCH_RESULTS_STEP=10,
    MIN_SEARCH_SCORE=0,
    MAX_SEARCH_SCORE=1,
    DEFAULT_SEARCH_MIN_SCORE=0.4,
    SEARCH_SCORE_STEP=0.05,
)

OLLAMA_EMBEDDING_TIMEOUT = 10
