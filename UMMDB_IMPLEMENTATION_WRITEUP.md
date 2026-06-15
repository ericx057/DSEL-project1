# UMMDB Implementation Write-Up

This write-up is based on the checked-in source, tests, scripts, deployment files, and generated graph artifacts in this repository. I am treating "files created" as the implementation files currently present in the repo; Git history does not provide a reliable creation narrative here. I am not filling gaps with assumed paper data.

Current verification state: `.venv\Scripts\python.exe -m pytest -q` passes with `120 passed in 63.73s`.

## 1. High-Level Shape

UMMDB is implemented as a codebase intelligence pipeline:

1. Identify or poll a repository.
2. Filter files that should not be indexed.
3. Parse source files into normalized `ParsedChunk` objects.
4. Convert chunks into stored artifacts and graph edges.
5. Persist artifacts, embeddings, and edges in SQLite.
6. Search by vector similarity and graph traversal under tier and repo-scope constraints.
7. Rerank and assemble retrieved chunks into a prompt.
8. Stream the prompt through a local inference engine or local demo client.
9. Cache, coalesce, audit, and record history around the query response.

The core UMMDB source is under `src/UMMDB`. Production integration lives mostly in `src/ingestion`, `src/retrieval`, `src/gateway`, `src/diagram`, and `src/inference`.

## 2. Core UMMDB Files

### `src/UMMDB/__init__.py`

Empty package marker. It makes `src/UMMDB` importable as a Python package.

### `src/UMMDB/input/__init__.py`

Empty package marker for input modules.

### `src/UMMDB/input/sync.py`

This file defines `RepoSynchronizer`, a small polling helper.

Code segments:

- Lines 1-2 import `os` and `subprocess`.
- Lines 4-8 define `RepoSynchronizer.__init__`. It stores:
  - `repo_path`: target repository path.
  - `poll_interval`: configured interval. The class stores it but does not sleep internally.
  - `last_commit`: last observed Git HEAD SHA.
- Lines 10-25 define `get_head_commit`.
  - It first returns `None` if `repo_path` is not a directory.
  - It runs `git rev-parse HEAD` with `cwd=self.repo_path`.
  - It returns the stripped commit SHA on success.
  - It returns `None` for Git errors or any other exception.
- Lines 27-36 define `poll`.
  - It calls `get_head_commit`.
  - If no commit exists, it returns `False`.
  - If the commit differs from `last_commit`, it updates `last_commit` and returns `True`.
  - If unchanged, it returns `False`.

Important integration note: this synchronizer is tested, but it is not wired into the production `docker-compose` or gateway bootstrap path. Production indexing is currently run as an explicit indexing command/container, not as an automatic poller.

### `src/UMMDB/parser/__init__.py`

Empty package marker for parser modules.

### `src/UMMDB/parser/cascade.py`

This is the parser contract and parser orchestration file.

Code segments:

- Lines 1-3 import dataclass utilities, typing helpers, and `os`.
- Lines 5-16 define `ParsedChunk`, the shared parser output model. Fields:
  - `content`: chunk text.
  - `fidelity`: parser fidelity label such as `L-1`, `L-2`, `L-3`, or `L-4`.
  - `metadata`: arbitrary parser metadata.
  - `symbol_name`: symbol name when known.
  - `line_start` and `line_end`: source line span.
  - `kind`: semantic kind such as `module`, `class`, `function`, `method`, or implementation variants.
  - `tier`: access tier as integer. `1` is interface-level, `3` is implementation-level.
  - `calls`: called symbol references.
  - `inherits`: inherited parent references.
- Lines 18-23 define `BaseParser`, a no-op interface. It returns `False` from `can_parse` and `[]` from `parse`.
- Lines 25-28 import the concrete parser implementations.
- Lines 30-38 define `CascadingParser.__init__`. Parser order is:
  1. `PythonAstParser`
  2. `TreeSitterParser`
  3. `CtagsParser`
  4. `RegexParser`
  5. `SlidingWindowParser`
- Lines 40-41 define `can_parse`, which always returns true because the cascade is designed to try every fallback.
- Lines 43-55 define `parse`.
  - Missing paths return `[]`.
  - For each parser, it calls `can_parse`.
  - If the parser can parse, it calls `parse`.
  - The first non-empty chunk list is returned.
  - Exceptions are swallowed so the next parser can try.

How it ties together: every downstream component depends on `ParsedChunk` shape. The cascade lets higher-fidelity parsers win while preserving eventual fallback behavior.

### `src/UMMDB/parser/python_ast.py`

This is the highest-fidelity parser for Python.

Code segments:

- Lines 1-5 import future annotations, `ast`, `Path`, and `Optional`.
- Lines 8-10 define `PythonAstParser.can_parse`. It accepts explicit `language="python"` or `.py` paths.
- Lines 12-38 define `PythonAstParser.parse`.
  - It imports `ParsedChunk` lazily from `cascade` to avoid circular import problems.
  - It rejects non-Python files.
  - It reads UTF-8 source.
  - It calls `ast.parse`.
  - Syntax errors return `[]`, allowing cascade fallback.
  - It creates one module-level tier-1 chunk covering the full file.
  - It runs `_PythonChunkVisitor` to collect classes, functions, methods, implementations, calls, and inheritance.
- Lines 41-49 define `_PythonChunkVisitor.__init__` and `collect`.
  - `parents` tracks nested class/function scope.
  - `chunks` accumulates output chunks.
- Lines 51-85 define `visit_ClassDef`.
  - It computes a qualified name.
  - It computes the class end line from `end_lineno`.
  - It extracts base-class names into `inherits`.
  - It emits a tier-1 interface chunk containing only the class signature.
  - It emits a tier-3 implementation chunk containing the full class source.
  - It pushes the class into `parents`, visits children, then pops it.
- Lines 87-91 route sync and async functions into `_visit_function`.
- Lines 93-128 define `_visit_function`.
  - It computes qualified name and kind. Top-level functions are `function`; nested class functions are `method`.
  - It collects calls through `_CallVisitor`.
  - It emits a tier-1 interface chunk containing only the signature and call references.
  - It emits a tier-3 implementation chunk containing the full source segment.
  - It visits nested content under the updated parent stack.
- Lines 130-151 are helpers:
  - `_qualified_name` joins parent names.
  - `_function_signature` returns `def name(args)` or `async def name(args)`.
  - `_class_signature` includes base classes when present.
  - `_name` resolves `ast.Name` and dotted `ast.Attribute` nodes.
- Lines 154-189 define `_CallVisitor`.
  - It visits only the root function/class body rather than collecting calls from nested definitions.
  - `visit_Call` converts the callee into a name.
  - `_append_name` stores both a dotted reference and its short name, deduped.

How it ties together: this parser produces the richest records. Tier-1 chunks are safe interface summaries; tier-3 chunks hold implementation detail. `calls` and `inherits` are later turned into graph edges by `RepositoryIndexer`.

### `src/UMMDB/parser/tree_sitter.py`

This parser provides a broad language fallback when tree-sitter and language grammars are installed.

Code segments:

- Lines 1-4 import OS/import helpers, `Path`, and typing.
- Lines 5-9 detect whether `tree_sitter` is importable.
- Lines 11-19 map language names to grammar module packages.
- Lines 21-33 map extensions to language names.
- Lines 35-37 initialize `TreeSitterParser` with a language cache.
- Lines 39-42 define `can_parse`.
  - It rejects if `tree_sitter` itself is unavailable.
  - It resolves the language and requires a loadable grammar.
- Lines 44-77 define `parse`.
  - It resolves and loads the language.
  - It reads the file.
  - It creates a `tree_sitter.Parser`.
  - It supports both newer `parser.language = ...` and older `parser.set_language(...)` APIs.
  - It rejects parse trees whose root has errors.
  - It returns a single module-level tier-2 chunk containing the whole file and parser metadata.
- Lines 79-83 resolve language from explicit argument or extension.
- Lines 85-100 load and cache the grammar.
  - Missing language modules or API failures become cached `None`.

How it ties together: tree-sitter is currently a whole-file fallback in this repo. It does not extract symbol-level Python metadata like the AST parser, but it gives a structured parser tier for non-Python languages.

### `src/UMMDB/parser/ctags.py`

This parser shells out to ctags for symbol-oriented fallback parsing.

Code segments:

- Lines 1-4 import subprocess/path helpers.
- Lines 6-16 define supported language names.
- Lines 18-32 map extensions to supported languages.
- Lines 34-43 define `CtagsParser.can_parse`.
  - It resolves language from explicit argument or extension.
  - It rejects unsupported languages.
  - It checks that `ctags --version` can run.
  - Missing ctags returns `False`.
- Lines 45-60 define `parse`.
  - It runs `ctags -x file_path`.
  - Each nonblank ctags output line becomes an `L-2` `ParsedChunk` with metadata `{"parser": "ctags"}`.
  - Exceptions are re-raised so `CascadingParser` can catch and continue.

How it ties together: ctags can provide symbol lines if AST/tree-sitter are unavailable or unsuitable, but it is less structured than `PythonAstParser`.

### `src/UMMDB/parser/fallback.py`

This file contains the two final parser fallbacks.

`RegexParser` segments:

- Lines 1-3 import regex/path helpers.
- Lines 5-7 define `can_parse`, which always returns true.
- Lines 9-21 define `parse`.
  - It reads UTF-8 content.
  - It infers Python only.
  - For Python or unknown extension, it calls `_parse_python`.
  - Exceptions are re-raised for cascade handling.
- Lines 23-25 map `.py` to Python.
- Lines 27-51 define `_parse_python`.
  - It scans lines for `def`, `async def`, or `class` starts.
  - It computes block end by indentation.
  - It emits `L-3`, tier-3 chunks with symbol, line span, and kind.
- Lines 53-65 define `_find_python_block_end`.
  - Blank lines remain in the block.
  - A later nonblank line with indentation less than or equal to the starting indentation ends the block.

`SlidingWindowParser` segments:

- Lines 67-76 validate `window_size` and `overlap`.
  - Window size must be positive.
  - Overlap must be non-negative and smaller than window size.
- Lines 78-79 always claim parse support.
- Lines 81-110 read the file and emit overlapping `L-4`, tier-3 chunks.
  - Empty files return `[]`.
  - Line spans are computed by counting newlines before each window boundary.
  - The cursor advances by `window_size - overlap`.

How it ties together: regex preserves approximate Python symbols when AST parsing fails. Sliding windows guarantee text can still be indexed when no parser returns structure.

### `src/UMMDB/parser/filters.py`

This file gates files before parsing.

Code segments:

- Lines 1-2 import `os`.
- Lines 3-7 define `FileHeuristics.__init__`.
  - `max_line_length`: rejects minified or pathological long-line text.
  - `max_binary_ratio`: rejects binary-looking files by null byte ratio.
  - `exclude_patterns`: simple substring path exclusions.
- Lines 9-38 define `is_human_readable`.
  - Missing paths return false.
  - Any configured exclude substring in the file path returns false.
  - Empty files return true.
  - It reads the first 8192 bytes and rejects high null-byte ratio.
  - It then reads text as UTF-8 and rejects any line exceeding `max_line_length`.
  - Unicode decode errors and general exceptions return false.

How it ties together: `RepositoryIndexer` uses this before parsing, so binary or generated-like text does not enter embeddings or graph storage.

### `src/UMMDB/summarizer/__init__.py`

Empty package marker for summarizer modules.

### `src/UMMDB/summarizer/hooks.py`

This file defines optional local model hooks for embeddings and summaries.

Code segments:

- Lines 1-2 import environment and typing.
- Lines 4-9 try to import `transformers` classes. Missing imports set them to `None`.
- Lines 11-35 define `EmbeddingHook.__init__`.
  - Default model: `nomic-ai/nomic-embed-text-v1.5`.
  - It can be forced into mock mode.
  - If not mocked and `UMMDB_MOCK_MODELS` is unset, it loads tokenizer/model using `local_files_only=True`.
  - `trust_remote_code` is configurable but defaults false.
  - Any load failure flips to mock mode.
- Lines 37-52 define `get_embeddings`.
  - Empty input returns `[]`.
  - Mock mode returns `[0.1, 0.2, 0.3]` for every text.
  - Real mode tokenizes, calls the model under `torch.no_grad()`, mean-pools last hidden states, and returns lists.
  - Runtime failures return mock vectors.
- Lines 54-68 define `LLMHook.__init__`.
  - Default model: `gpt2`.
  - It loads tokenizer and causal LM locally only.
  - Failures switch to mock mode.
- Lines 70-84 define `summarize`.
  - Empty text returns empty string.
  - Mock mode returns a short prefix summary.
  - Real mode tokenizes up to 512 tokens and generates up to 50 new tokens.
  - Runtime failures fall back to the mock summary shape.

Important integration note: these hooks are covered by tests but are not the production embedding path used by the gateway/indexer. Production embeddings use `src/retrieval/embeddings.py` or `HashingEmbeddingProvider`.

### `src/UMMDB/summarizer/code_graph.py`

This is a thin NetworkX graph utility.

Code segments:

- Lines 1-2 import NetworkX and typing.
- Lines 4-6 define `CodeGraph` and initialize a directed graph.
- Lines 8-9 add nodes with optional metadata.
- Lines 11-12 add directed edges with a relationship type.
- Lines 14-18 return betweenness centrality, or `{}` for an empty graph.
- Lines 20-34 compute a threshold by percentile and return nodes whose centrality is at or above it.

How it ties together: conceptually, `ParsedChunk.calls` and `ParsedChunk.inherits` can feed this graph. In production, graph persistence is handled by `SQLiteUnifiedStore` edges instead.

## 3. Ingestion and Storage Integration

### `src/ingestion/indexer.py`

This is the central bridge from UMMDB parser output into persisted retrieval data.

Code segments:

- Lines 1-12 import dataclasses, paths, typing, UMMDB parser/filter classes, and retrieval record/store types.
- Lines 15-23 define `IndexReport`, the indexing result:
  - repository name
  - files indexed
  - files skipped
  - artifacts indexed
  - edges indexed
  - skip counts by reason
- Lines 25-53 define static skip and sensitivity rules.
  - `DEFAULT_EXCLUDES`: directories such as `.git`, `.venv`, `node_modules`, `dist`, `.cis`.
  - `SENSITIVE_FILENAMES`: `.env`, SSH keys, credentials, kubeconfig.
  - `SENSITIVE_SUFFIXES`: key/cert file suffixes.
  - `SECRET_PATTERNS`: private key headers and key/password/token assignments.
- Lines 55-65 initialize `RepositoryIndexer`.
  - It receives a `SQLiteUnifiedStore`.
  - It can receive custom heuristics, exclusions, or parser.
  - Default parser is `CascadingParser`.
- Lines 67-110 define `index_repository`.
  - Resolve and validate repo root.
  - Delete existing artifacts/edges for that repository. This makes indexing a full refresh per repo.
  - Iterate files.
  - Skip excluded path parts, sensitive paths, and non-human-readable files.
  - Index each file.
  - Files producing no artifacts are skipped with a reason.
  - Bulk upsert artifacts, then edges.
  - Return `IndexReport`.
- Lines 112-119 iterate files and check excluded path parts.
- Lines 121-131 detect sensitive paths.
  - It checks every relative path part lowercased.
  - It catches exact sensitive names, `.env.*`, sensitive suffixes, `secret`, and `secrets`.
- Lines 133-168 define `_index_file`.
  - Compute relative path and language.
  - Read file content.
  - Generated files produce one module artifact with metadata `{"generated": True}` and no edges.
  - Secret-looking content produces no artifacts.
  - Otherwise call `self.parser.parse`.
  - If parser returns chunks, call `_index_chunks`.
  - If not, call `_index_text_file`.
- Lines 170-210 define `_index_chunks`.
  - For each `ParsedChunk`, compute stable artifact ID.
  - Create `ArtifactRecord` with repo, path, language, text, tier, fidelity, symbol, line span, kind, and metadata.
  - Track tier-1 non-module chunk IDs by qualified name and short name.
  - Build graph edges after all chunks are known.
- Lines 212-244 define `_build_edges`.
  - Only tier-1 non-module chunks become graph edge sources.
  - `calls` become `calls` edges.
  - `inherits` become `inherits` edges.
  - Symbol references are resolved through qualified IDs and short-name IDs.
- Lines 246-258 define `_append_edge`.
  - It ignores self-edges.
  - It deduplicates by `(source_id, target_id, relationship)`.
- Lines 260-277 compute chunk symbol and qualified name.
- Lines 279-302 resolve symbol references.
  - Exact dotted reference wins.
  - `self.` and `cls.` are scoped to the current class when possible.
  - Dotted references can fall back to their short final component.
  - Short-name resolution only succeeds when exactly one candidate exists.
- Lines 304-328 define `_index_text_file`.
  - Non-parser text falls back to the first 4000 characters.
  - Empty text returns no artifacts.
  - The fallback artifact is tier-3, `L-4`, kind `chunk`.
- Lines 330-333 build IDs as `repository:relative_path:safe_symbol:T<tier>`.
- Lines 335-356 map file extensions to language labels, falling back to MIME guess or `text`.
- Lines 358-362 detect generated file headers.
- Lines 364-367 scan the first 8192 characters for secret patterns.

How it ties together: `RepositoryIndexer` is where UMMDB becomes queryable. It consumes `ParsedChunk`, assigns access tiers, produces `ArtifactRecord`s for vector search, and produces `GraphEdgeRecord`s for graph search.

### `src/ingestion/cli.py`

This is the production indexing command.

Code segments:

- Lines 1-8 import env/path helpers, indexer, store, and embedding providers.
- Lines 11-18 define `build_embedding_provider`.
  - `CIS_EMBEDDING_BACKEND=hashing` selects `HashingEmbeddingProvider`.
  - Otherwise it selects `LocalTransformersEmbeddingProvider`.
  - Default transformer model: `nomic-ai/nomic-embed-text-v1.5`.
  - `CIS_EMBEDDING_TRUST_REMOTE_CODE` toggles trust-remote-code.
- Lines 21-39 define `main`.
  - Read `CIS_DATA_DIR`, default `/data`.
  - Read required `CIS_REPOSITORY_PATH`.
  - Read `CIS_REPOSITORY_NAME`, defaulting to repo path name.
  - Ensure data dir exists.
  - Validate repo path is a directory.
  - Open `/data/index.db`.
  - Run `RepositoryIndexer`.
  - Print counts from `IndexReport`.

How it ties together: in Docker, the indexer service runs this module and writes the same SQLite database the gateway later reads.

### `src/retrieval/database.py`

This file defines retrieval storage and the default hashing embedding implementation.

Code segments:

- Lines 17-37 define `UnifiedStore`, the abstract contract for `vector_search` and `graph_search`.
- Lines 39-60 define `InMemoryUnifiedStore`, a test/dummy store filtering only by tier.
- Lines 63-76 define `ArtifactRecord`.
  - This mirrors stored artifact columns.
  - It includes id, repository, path, language, text, tier, fidelity, symbol, line span, kind, metadata.
- Lines 79-83 define `GraphEdgeRecord`.
- Lines 86-109 define `HashingEmbeddingProvider`.
  - It validates dimensions are at least 4.
  - It tokenizes identifiers/words with regex.
  - It hashes each lowercased token with SHA256.
  - It maps token hash to vector bucket.
  - It uses a hash byte as sign.
  - It L2-normalizes nonzero vectors.
  - This is not a learned embedding model.
- Lines 112-150 define query stopwords for signal extraction.
- Lines 153-160 initialize `SQLiteUnifiedStore`.
  - Store path is converted to `Path`.
  - Embedding provider defaults to `HashingEmbeddingProvider`.
  - A reentrant lock protects SQLite connection access.
  - A `check_same_thread=False` SQLite connection is opened.
  - Schema is initialized.
- Lines 162-170 close the connection safely.
- Lines 172-213 define schema.
  - `artifacts` stores text, embedding JSON, metadata JSON, tier, fidelity, source span, and timestamps.
  - Indexes support tier/repo and symbol lookups.
  - `edges` stores source, target, and relationship with a composite primary key.
- Lines 215-259 define `upsert_artifacts`.
  - For each artifact, compute embedding from artifact text.
  - Insert or update all artifact fields.
  - Store embedding as JSON.
  - Store metadata as sorted JSON.
- Lines 260-268 define `upsert_edges` with `INSERT OR IGNORE`.
- Lines 270-276 define `delete_repository`.
  - Finds existing artifact IDs for a repository.
  - Deletes edges referencing those IDs.
  - Deletes artifacts for that repository.
- Lines 278-298 define `vector_search`.
  - Embed query.
  - Select artifacts allowed by tier and repo scope.
  - Compute cosine dot product.
  - Add a small keyword bonus per query term present in symbol/text.
  - Sort by score descending.
  - Return top-k.
- Lines 300-328 define `graph_search`.
  - Select only allowed artifacts.
  - Find anchor artifact IDs by query terms.
  - If none, fallback to vector top 3.
  - Breadth-first traverse outgoing edges up to depth and breadth.
  - Only allowed target artifacts are visited.
- Lines 330-351 define `list_edges`, filtered by allowed artifacts and optional relationship.
- Lines 353-358 define `list_artifacts`.
- Lines 360-368 define `get_artifacts_by_ids`, tier-filtered but not repo-scope-filtered.
- Lines 370-383 centralize tier and repo-scope filtering.
  - `tier <= user_tier`.
  - If `repo_scope` is an empty list, return no rows.
  - If scope is present, require repository in scope.
- Lines 385-402 find graph anchors by signal terms across id, symbol, file path, text, and metadata.
- Lines 404-410 extract signal terms from query.
- Lines 412-421 load outgoing edges, ordered by relationship priority.
- Lines 423-427 compute cosine. Since vectors are normalized, this is a dot product.
- Lines 429-444 convert SQLite rows to public dictionaries and parse metadata JSON.

How it ties together: this store is both the embedding index and graph index. It is intentionally simple: vectors are stored as JSON in SQLite and scored in Python.

### `src/retrieval/embeddings.py`

This file defines the learned local embedding provider used by production configuration when hashing is not selected.

Code segments:

- Lines 7-12 define the `EmbeddingProvider` protocol.
- Lines 15-30 initialize `LocalTransformersEmbeddingProvider`.
  - It imports `torch`, `AutoModel`, and `AutoTokenizer`.
  - It loads tokenizer/model with `local_files_only=True`.
  - Default model is `nomic-ai/nomic-embed-text-v1.5`.
  - It sets the model to eval mode.
- Lines 32-43 embed one or many texts.
  - Tokenize with padding/truncation.
  - Run model under no-grad.
  - Mean-pool last hidden states.
  - Normalize each vector.
- Lines 45-50 implement L2 normalization.

How it ties together: `src/ingestion/cli.py` and `src/gateway/bootstrap.py` use this provider by default unless `CIS_EMBEDDING_BACKEND=hashing`.

### `src/retrieval/hybrid.py`

This file merges vector and graph retrieval.

Code segments:

- Lines 4-19 define `HybridSearcher`.
  - It accepts a `UnifiedStore`.
  - `lambda_ratio` must be between 0 and 1.
  - It stores vector top-k, graph depth, and graph breadth.
- Lines 21-42 define `search`.
  - `lambda_ratio == 1.0`: vector only.
  - `lambda_ratio == 0.0`: graph only.
  - Otherwise run both.
  - It takes an initial slice of vector results based on lambda.
  - Then appends graph results.
  - Then appends remaining vector results.
  - Deduplicates by artifact ID while preserving this order.

How it ties together: gateway prompt building uses the default `HybridSearcher(store)` with `lambda_ratio=0.5`.

### `src/retrieval/reranker.py`

This file contains two rerankers.

Code segments:

- Lines 4-18 lazily load `sentence_transformers.CrossEncoder`.
- Lines 20-52 define `Reranker`.
  - In non-mock mode it loads `cross-encoder/ms-marco-MiniLM-L-6-v2` with local files only.
  - Mock mode scores by query-word overlap.
  - Real mode predicts scores for `[query, chunk_text]` pairs.
  - It sorts by `rerank_score` and returns top-m.
- Lines 55-142 define `LexicalReranker`.
  - It removes stopwords from query terms.
  - It searches id, symbol, file path, kind, text, and metadata.
  - It scores overlap, exact symbol matches, exact file path match, exact kind match, and interface preference.
  - It sorts by rerank score, then original search score.

How it ties together: production gateway prompt building uses `LexicalReranker`, not the cross-encoder `Reranker`. The cross-encoder class exists and is tested, but is not called in `src/gateway/main.py`.

### `src/retrieval/assembler.py`

This file builds the model prompt.

Code segments:

- Lines 3-5 define `PromptAssembler` with optional system rule.
- Lines 7-15 define `_u_shape_order`.
  - Even-indexed chunks go left.
  - Odd-indexed chunks go right.
  - Return left plus reversed right.
  - This places high-ranked chunks near both beginning and end of context.
- Lines 17-34 define `assemble`.
  - Add system rule if present.
  - If chunks exist, add `Context:`.
  - For each ordered chunk, emit a file/language/tier header and text.
  - Always append `Query: ...`.

How it ties together: gateway passes reranked chunks into this assembler before inference.

## 4. Gateway and Query Flow

### `src/gateway/models.py`

Defines Pydantic/domain models.

Segments:

- Lines 5-8 define `AccessTier`.
  - `T-1`: interface only.
  - `T-2`: summary level.
  - `T-3`: implementation level.
- Lines 10-12 define authenticated `User`.
- Lines 14-18 define `QueryRequest`.
  - `extra="forbid"` blocks request-side model override fields.
  - `diagram_requested` exists but is not used by `/query`.
- Lines 20-28 define `AuditEvent`.
- Lines 30-36 define `HistoryRecord`.

### `src/gateway/security.py`

Defines HS256 JWT verification.

Segments:

- Lines 15-21 configure secret, optional issuer, optional audience.
- Lines 23-47 verify authorization.
  - Extract bearer token.
  - Split JWT into header/payload/signature.
  - Decode JSON.
  - Require `alg=HS256`.
  - Verify HMAC-SHA256 signature.
  - Validate claims.
  - Normalize `groups` to a list.
  - Return `User`.
- Lines 49-64 validate subject, expiration, issuer, and audience.
- Lines 66-80 extract bearer token and base64url-decode segments.

### `src/gateway/repositories.py`

Defines persistence contracts and SQLite implementations for auth/scope/audit/history.

Segments:

- Lines 12-20 migrate old `model_used` columns to `inference_engine_used` where needed.
- Lines 22-84 define abstract repository contracts:
  - `AccessMatrixRepository`
  - `ScopeRepository`
  - `CacheRepository`
  - `RateLimitRepository`
  - `AuditRepository`
  - `UserHistoryRepository`
- Lines 87-132 implement `SQLiteAccessMatrixRepository`.
  - Table: `access_matrix(user_id, tier)`.
  - Unknown users default to `AccessTier.T1`.
- Lines 135-180 implement `SQLiteScopeRepository`.
  - Table: `group_scopes(group_name, repository)`.
  - Groups map to repositories.
  - Scope resolution ignores query text currently.
- Lines 183-258 implement `SQLiteAuditRepository`.
  - Table: `audit_log`.
  - Records user, tier, query hash, repo scope, inference engine, latency, cache hit, RBAC block.
- Lines 261-329 implement `SQLiteUserHistoryRepository`.
  - Table: `user_history`.
  - Stores full query/response plus engine, scope, created time.
  - Lists most recent rows for a user.

### `src/gateway/services.py`

Defines gateway business services and cache/rate-limit implementations.

Segments:

- Lines 17-45 define `CircuitBreaker`.
  - Closed allows requests.
  - Failures increment count.
  - At threshold, state becomes open.
  - After recovery timeout, open becomes half-open.
  - Success resets to closed.
- Lines 47-58 define `IAMService`.
  - JWT decode delegates to verifier.
  - Tier lookup delegates to access repository.
- Lines 60-65 define `ScopingService`.
  - Delegates group-to-repo resolution.
- Lines 67-99 define `CacheService`.
  - Cache key is SHA256 of query, tier, and sorted scopes.
  - T3 cache TTL is 3600 seconds.
  - T1/T2 cache TTL is 14400 seconds.
  - It wraps get/set/lock/pubsub/release on the cache repository.
- Lines 101-113 define `RateLimitService`.
  - Checks circuit breaker first.
  - Delegates token consumption to rate limit repository.
- Lines 115-120 define `AuditService`.
- Lines 123-170 implement in-memory semantic cache.
  - Stores response plus expiry.
  - Tracks locks for request coalescing.
  - Tracks subscriber queues per cache key.
  - Release sends `None` to close subscribers.
- Lines 173-190 implement token bucket rate limiting.
  - Per-user tokens refill over time.
  - One token is consumed per query.
- Lines 193-244 implement Redis cache.
  - Response keys are `cis:cache:<hash>`.
  - Lock keys are `cis:lock:<hash>`.
  - Stream channels are `cis:stream:<hash>`.
  - Redis `SET NX EX` implements lock acquisition.
  - `__END__` terminates subscribers.
- Lines 247-252 map `AccessTier` enum values to numeric tier ranks.

### `src/gateway/main.py`

This is the FastAPI application and primary query path.

Segments:

- Lines 36-68 declare global circuit breaker and dependency placeholders.
- Lines 71-95 define service dependency constructors.
- Lines 98-142 define `create_app`.
  - Accepts concrete repositories, retrieval store, model hook, JWT verifier, and metrics token.
  - Builds a FastAPI app.
  - Adds security headers.
  - Registers dependency overrides when concrete instances are passed.
- Lines 144-146 expose `/health`.
- Lines 148-158 expose `/history`.
  - Authenticates user.
  - Returns history if configured.
- Lines 160-174 expose `/diagram/call-graph`.
  - Authenticates.
  - Resolves tier and scopes.
  - Renders SVG from `DiagramService`.
- Lines 176-198 expose `/metrics`.
  - If metrics token is configured, request must provide matching header or bearer token.
  - Exposes circuit breaker state/failures in Prometheus text format.
- Lines 200-299 define `POST /query`.
  - Start timer.
  - Decode JWT.
  - Check circuit breaker and rate limit.
  - Resolve tier and repo scopes.
  - Build query hash/cache key.
  - If no scope, audit RBAC block and return 403.
  - Check cache. On hit, audit and return JSON.
  - Acquire per-key lock.
  - If lock is held by another identical query, subscribe to its stream.
  - If lock acquired, build retrieval prompt.
  - Stream chunks from selected model hook.
  - Publish chunks to subscribers while yielding to the current HTTP response.
  - Cache final response.
  - Add history row.
  - Audit final request.
  - Release lock in `finally`.
- Lines 304-315 define `_build_prompt`.
  - Require configured store.
  - Run hybrid search using numeric tier and scopes.
  - Lexically rerank to top 8 chunks.
  - Add read-only system rule containing user access tier.
  - Assemble prompt.
- Line 318 creates the module-level `app` with no concrete dependencies. Tests and bootstrap override dependencies.

How it ties together: this is where auth, scope, tier, cache, retrieval, prompt assembly, and inference meet.

### `src/gateway/model_hook.py`

This is the async inference bridge for gateway streaming.

Segments:

- Lines 17-25 define `TextGenerationClient` protocol.
- Lines 28-72 define `LlamaCppCompletionClient`.
  - It resolves endpoint URL from explicit endpoint, base URL, or `CIS_LLAMA_CPP_BASE_URL`.
  - It posts to `/completion`.
  - Payload includes `prompt`, `stream`, `n_predict`, and `cache_prompt`.
  - It streams response lines with timeout and max stream duration.
  - `decode_stream_line` parses each response line.
- Line 74 aliases `HttpInferenceEngineClient`.
- Lines 77-104 define `ModelHook`.
  - Default engine id is `llama.cpp`.
  - Default client is `LlamaCppCompletionClient`.
  - `generate_stream` yields chunks.
  - Success records circuit breaker success.
  - Failure records circuit breaker failure and yields a visible inference error marker.

### `src/gateway/bootstrap.py`

This is production app wiring.

Segments:

- Lines 23-31 read core env and create `/data`.
  - Requires `CIS_JWT_SECRET`.
  - Requires `CIS_METRICS_TOKEN`.
- Lines 33-41 choose embedding provider.
  - `CIS_EMBEDDING_BACKEND=hashing` selects hashing.
  - Otherwise default local transformer model is `nomic-ai/nomic-embed-text-v1.5`.
- Line 43 opens `/data/index.db`.
- Lines 45-53 configure access and scopes.
  - Optional bootstrap user tier.
  - Optional bootstrap group scope for repository name.
- Lines 55-56 choose Redis or in-memory cache.
- Lines 58-68 call `create_app` with SQLite repositories, cache, rate limiting, audit, history, retrieval store, JWT verifier, and metrics token.
- Lines 70-74 serve the frontend at `/`.

How it ties together: gateway and indexer share `/data/index.db`, normally through the Docker `cis-data` volume.

### `src/gateway/tool_gateway.py`

This file executes callable tools under timeout and scope checks.

Segments:

- Lines 8-10 define timeout in seconds.
- Lines 12-42 define `execute`.
  - Rejects when `resource_scope` is outside `permitted_scopes`.
  - Runs the tool under `asyncio.wait_for`.
  - Timeout returns a structured error observation.
  - Exceptions return structured failure observations.
- Lines 43-49 define `_run_tool`.
  - Await coroutine functions directly.
  - Run sync functions in executor.

This is separate from the UMMDB retrieval path but follows the same scope-control idea.

## 5. Diagram, Inference, Deployment, and Demo

### `src/diagram/service.py`

Renders a visible call graph as SVG.

Segments:

- Lines 9-11 store `SQLiteUnifiedStore`.
- Lines 13-20 query visible graph nodes and visible `calls` edges.
- Lines 21-26 compute simple horizontal layout.
- Lines 27-36 create SVG line markup for edges.
- Lines 37-46 create SVG node rectangles and labels.
- Lines 47-53 return final SVG with arrow marker.

Tier and scope filtering happen inside `store.graph_search` and `store.list_edges`.

### `src/inference/llamacpp.py`

Contains llama.cpp deployment/config helpers.

Segments:

- Lines 9-29 define `LlamaCppPrecision`.
  - Valid values: `fp16`, `fp8`, `fp4`.
  - Cache type mapping: `fp16 -> f16`, `fp8 -> q8_0`, `fp4 -> q4_0`.
- Lines 32-56 define `LlamaCppEndpointConfig`.
  - Normalizes base URL.
  - Strips trailing `/completion` if provided.
  - Provides `/completion` and `/health`.
- Lines 59-127 define `LlamaCppServerSettings`.
  - Reads precision, VRAM/RAM settings, GPU layer setting, context window, batch sizes, flash attention, mmap, prompt cache.
  - Validates positive context window.
  - Resolves precision-specific model path from env.
  - Converts settings into `LLAMA_ARG_*` env vars.
- Lines 129-130 encode booleans as `true`/`false`.

### `src/inference/runtime.py`

Defines synchronous runtime abstraction and llama.cpp runtime.

Segments:

- Lines 12-15 define `InferenceRuntime`.
- Lines 18-47 define `LlamaCppRuntime`.
  - Resolve `/completion` endpoint.
  - POST prompt with `stream=True` and `cache_prompt=True`.
  - Iterate streaming lines.
  - Yield tokens until done.
- Lines 50-52 define `HttpInferenceRuntime` alias wrapper.
- Lines 55-61 define `MockRuntime`.
- Lines 64-98 define `decode_stream_line`.
  - Handles empty lines.
  - Handles Server-Sent Event `data:` prefix.
  - Handles `[DONE]`.
  - Parses JSON for llama.cpp native `content`, OpenAI-compatible `choices`, `response`, `token`, `text`, or `delta`.
  - Returns `(token, done)`.

### `src/inference/registry.py`

Defines the current inference endpoint registry.

Segments:

- Lines 10-14 define `InferenceEngineEndpoint`.
- Lines 17-27 store endpoint/base URL and engine ID.
- Lines 28-34 return a normalized completion and health endpoint.

Important note: tests explicitly assert this registry no longer exposes model selection methods such as `get_available_models` or `get_model_for_task`.

### `src/inference/hardware.py`

Defines simple hardware profiling.

Segments:

- Lines 4-6 return `0` GPU VRAM. GPU detection is currently stubbed.
- Lines 8-34 detect system RAM.
  - Windows uses `GlobalMemoryStatusEx`.
  - POSIX uses `os.sysconf`.
  - Failures return `0`.
- Lines 36-46 choose profile.
  - `gpu-dual` for VRAM >= 32 GB.
  - `gpu-single` for VRAM >= 16 GB.
  - `cpu-large` for RAM >= 32 GB.
  - otherwise `cpu-small`.

### `src/inference/queue.py`

Defines a blocking request queue primitive.

Segments:

- Lines 4-5 define `ServiceUnavailableError`.
- Lines 7-14 initialize max concurrent requests, max queue depth, counters, lock, and condition.
- Lines 16-33 define request context manager.
  - If active requests are at capacity and queue is full, raise 503-style error.
  - Otherwise increment queue depth and wait.
  - On entry, increment active requests.
  - On exit, decrement active requests and notify one waiter.

### `docker-compose.yml`

Production composition.

Segments:

- Lines 2-24 define `gateway`.
  - Builds local Dockerfile.
  - Publishes port 8000.
  - Provides data dir, repository name/path, JWT settings, metrics token, llama.cpp URL, Redis URL, bootstrap values.
  - Mounts `cis-data:/data`.
  - Depends on Redis and llama.cpp.
- Lines 26-40 define `indexer`.
  - Command: `python -m src.ingestion.cli`.
  - Profile: `indexing`.
  - Mounts the current repo read-only at `/repos/project1`.
  - Shares `cis-data:/data`.
- Lines 42-45 define internal Redis.
- Lines 47-72 define internal llama.cpp server.
  - Uses `ghcr.io/ggml-org/llama.cpp:server-cuda` by default.
  - Exposes 8080 internally, not to host.
  - Mounts model directory and entrypoint.
  - Reserves one Nvidia GPU.
- Lines 74-82 define Prometheus.
- Lines 84-85 define `cis-data` volume.

### `Dockerfile`

Production image.

Segments:

- Line 1 uses `python:3.13-slim`.
- Lines 3-5 configure unbuffered Python and `PYTHONPATH=/app/src`.
- Lines 6-11 install dependencies and copy `src`.
- Lines 13-17 create non-root `cisuser`, create `/data`, and switch users.
- Line 19 exposes 8000.
- Line 21 runs `uvicorn src.gateway.bootstrap:app`.

### `scripts/llamacpp-entrypoint.sh`

llama.cpp container entrypoint.

Segments:

- Lines 1-2 set shell mode.
- Lines 4-26 resolve precision and default KV cache type.
- Lines 28-32 require a model path, either generic or precision-specific.
- Lines 34-36 set model, host, and port env vars for llama-server.
- Lines 37-48 validate positive context window.
- Lines 49-58 set batch, ubatch, GPU layers, KV offload, cache type, prompt cache, flash attention, mmap, and metrics env.
- Line 60 executes `/app/llama-server`.

### `.env.example`

Documents expected configuration:

- JWT and metrics secrets.
- llama.cpp base URL/image/model paths/precision/context/GPU settings.
- repository name.
- embedding backend/model/trust-remote-code.
- bootstrap user/group/tier.
- local demo JWT settings.

### `run_demo.py`

Local development bootstrap.

Segments:

- Lines 34-40 define `DemoContextBlock`.
- Lines 42-127 define `LocalDemoCompletionClient`.
  - Parses prompt context blocks of the format emitted by `PromptAssembler`.
  - Extracts the query.
  - Returns a deterministic text response listing top retrieved context.
  - Chunks the response for streaming.
- Lines 129-145 define `LocalDemoModelHook`.
  - Streams from the local demo client.
  - Records circuit breaker success/failure.
- Lines 148-150 choose local-demo inference unless `CIS_LOCAL_USE_LLAMA_CPP` is truthy.
- Lines 153-172 create a local HS256 dev token.
- Lines 175-184 pick a free local port.
- Lines 187-222 define local app bootstrap.
  - Creates `.cis`.
  - Requires `CIS_LOCAL_JWT_SECRET`.
  - Opens `.cis/index.db`.
  - Indexes the current project as repository `project1`.
  - Sets local user tier.
  - Grants `engineering -> project1`.
  - Uses in-memory cache and SQLite audit/history.
  - Uses local demo model by default.
  - Serves frontend.
- Lines 225-240 run uvicorn and print URL/token/inference mode.

Important note: `run_demo.py` indexes the current project at startup. That is local demo behavior, not production container behavior.

## 6. How the Pieces Move Together

### Indexing Flow

1. `src.ingestion.cli` reads repo/data/model config from env.
2. It creates `SQLiteUnifiedStore`.
3. It creates `RepositoryIndexer`.
4. `RepositoryIndexer.index_repository` clears prior rows for that repository.
5. It walks files under the repo root.
6. It skips excluded, sensitive, binary, too-long-line, generated, or secret-pattern files.
7. It calls `CascadingParser.parse`.
8. `CascadingParser` tries Python AST first, then tree-sitter, ctags, regex, and sliding window.
9. Parser output is normalized as `ParsedChunk`.
10. Chunks become `ArtifactRecord`s.
11. Tier-1 interface chunks with calls/inherits become graph edge sources.
12. Edges are resolved by qualified names, class-scoped `self.`/`cls.`, and unambiguous short names.
13. Artifacts are embedded and upserted.
14. Edges are inserted idempotently.
15. `IndexReport` returns counts and skip reasons.

### Query Flow

1. Client posts `{"query": "..."}` to `/query` with bearer JWT.
2. Gateway verifies JWT.
3. Gateway checks circuit breaker.
4. Gateway checks per-user token bucket.
5. Gateway loads user access tier.
6. Gateway resolves allowed repo scopes from user groups.
7. Empty scope is audited and blocked with 403.
8. Gateway hashes query, tier, and scopes into a cache key.
9. Cache hit returns immediately and audits cache hit.
10. Cache miss tries to acquire a per-key lock.
11. If another identical request is already running, this request subscribes to that stream.
12. The lock owner builds a retrieval prompt.
13. Hybrid search gets vector and graph results from allowed artifacts only.
14. Lexical reranker selects top 8.
15. Prompt assembler formats context blocks and query.
16. `ModelHook` streams llama.cpp or test/demo client output.
17. Each chunk is published to subscribers and yielded to the HTTP response.
18. Final response is cached.
19. History row is saved.
20. Audit row is saved.
21. Lock is released and subscribers terminate.

### Synchronization

There are several synchronization meanings in this implementation:

- Git sync: `RepoSynchronizer` can detect HEAD changes, but no production caller is wired.
- Index/data sync: production indexer and gateway share `/data/index.db` through Docker volume `cis-data`.
- Repository refresh sync: `RepositoryIndexer` uses `delete_repository(repository)` before writing new artifacts, so a reindex is a full per-repo replacement.
- SQLite thread sync: `SQLiteUnifiedStore` and SQLite gateway repositories use `threading.RLock` and `check_same_thread=False`.
- Query coalescing sync: `CacheService.acquire_lock` ensures identical concurrent queries share one inference request.
- Stream sync: in-memory cache uses `asyncio.Queue`; Redis cache uses pub/sub channels.
- Cache sync: cache keys include query, access tier, and sorted repo scopes, so data for one authorization context does not satisfy another.
- Access sync: tier filtering is applied inside retrieval selection, not only at prompt time.
- Scope sync: repo scope filtering is applied inside retrieval selection and diagram edge listing.

## 7. Tests and What They Prove

Current test run: `120 passed`.

Important test groups:

- `tests/UMMDB/input/test_sync.py`
  - Missing repo returns no commit and no poll event.
  - Empty Git repo has no HEAD.
  - First commit and second commit both trigger `poll=True`.
  - Subprocess errors are swallowed into `None`.
- `tests/UMMDB/parser/test_cascade.py`
  - Missing files return `[]`.
  - Cascade skips incapable parsers and thrown exceptions.
  - Python AST parser wins for Python.
- `tests/UMMDB/parser/test_python_ast.py`
  - Module chunks, class inheritance, method calls, line ranges, implementation chunks, and fidelity are validated.
- `tests/UMMDB/parser/test_tree_sitter.py`
  - Missing library or grammar fails gracefully.
- `tests/UMMDB/parser/test_ctags.py`
  - ctags availability, missing binary, symbol conversion, blank output, and exceptions are covered.
- `tests/UMMDB/parser/test_fallback.py`
  - Regex Python extraction and sliding-window chunking are covered.
- `tests/UMMDB/parser/test_filters.py`
  - Missing, excluded, empty, binary, long-line, invalid UTF-8, exception, and normal text paths are covered.
- `tests/UMMDB/summarizer/test_hooks.py`
  - Mock mode, local load fallback, and runtime fallback are covered for embeddings and LLM summaries.
- `tests/production/test_repository_indexer.py`
  - Tiered artifacts and graph edges.
  - Excluded/binary skips.
  - Sensitive path and secret pattern skips.
  - Injected UMMDB parser integration.
  - Method call resolution without short-name collision.
- `tests/production/test_sqlite_unified_store.py`
  - Vector search filters by tier and repo scope.
  - Graph search walks only allowed artifacts.
- `tests/gateway/test_production_query_flow.py`
  - Retrieval happens before inference.
  - T1 users do not receive T3 implementation context.
  - Audit and history are written.
  - Model override is rejected.
  - Metrics endpoint requires token.
  - No-scope queries are blocked and audited.
- `tests/gateway/test_main.py`
  - Query flow, rate limiting, cache hit, request coalescing.
- `tests/diagram/test_diagram_service.py`
  - SVG includes visible nodes and hides tier-inaccessible nodes.
- `tests/inference/*`
  - llama.cpp endpoint/settings/runtime parsing.
  - queue backpressure.
  - hardware profile thresholds.

## 8. Paper/Result Evidence in This Repo

There is no checked-in paper result table in this repo.

Evidence:

- `benchmarks/` exists but is empty.
- No local CSV/JSON/Markdown benchmark table is present under `benchmarks`, `plans`, `scripts`, `src/evaluation`, or `tests/evaluation`.
- `plans/domain4-implementation.md` is an implementation plan for inference engine work, not a results document.
- `graphify-out/GRAPH_REPORT.md` is a structural graph report, not a benchmark result table.

### Repositories Used

The concrete repositories evidenced locally are:

1. `project1`
   - Used by `run_demo.py`.
   - `run_demo.py` indexes the current repo root as repository name `project1`.
   - Docker compose also uses `CIS_REPOSITORY_NAME=project1` and mounts the current repo to `/repos/project1` for indexing.

2. Synthetic `repo-a`
   - Created in tests under temporary directories.
   - Used by production indexer tests and SQLite/gateway tests.
   - These are small synthetic files, not real external repos.

3. Arbitrary external repo path for parser QA
   - `scripts/qa_ummdb_parser.py` takes a positional `repo_path`.
   - The class is named `FlaskParserQa`.
   - The indexer repository name inside that script is `flask-qa`.
   - There is no Flask checkout or recorded Flask QA output checked in.

4. Synthetic `gold.jsonl`
   - `tests/evaluation/test_framework.py` creates a temporary `gold.jsonl` only to test SHA256 manifesting.

### How Results Are Measured

There are four result-like mechanisms:

#### 1. Unit and integration tests

Measured by pytest assertions. Current local run passes: `120 passed`.

This verifies behavior but is not a paper benchmark.

#### 2. Parser QA script

File: `scripts/qa_ummdb_parser.py`.

Measurement logic:

- It walks `.py` files under a supplied repo path.
- It parses each file with Python `ast`.
- `_ExpectedSymbolVisitor` builds expected class/function/method symbols.
- It records:
  - qualified name
  - kind
  - start line
  - end line
  - calls
  - inheritance
- It samples up to `--n`, default `30`, using `--seed`, default `1337`.
- It parses sampled files with `CascadingParser`.
- A sample passes if:
  - interface chunk exists,
  - implementation chunk exists,
  - interface line start matches,
  - implementation line end matches,
  - calls match,
  - inheritance matches.
- It reports:
  - `repo_path`
  - `sample_size`
  - `seed`
  - `symbols_available`
  - `passed`
  - `failed`
  - `accuracy = passed / len(sample)`
  - `index_report`
  - detailed failures
- It also runs `RepositoryIndexer` against the supplied repo using repository name `flask-qa`.
- It stores temporary QA index at `repo_path.parent / "ummdb_qa_index.db"`.

No execution output from this script is checked in.

#### 3. Evaluation framework

File: `src/evaluation/framework.py`.

It currently contains:

- `DatasetManifest.from_file`, which computes SHA256 for a dataset path.
- `RefusalPrecisionScorer`, which returns `1` only when a response is a refusal and does not leak code-like details.

The corresponding test only proves stable hashing and the refusal scorer's binary behavior. It does not run a retrieval benchmark.

#### 4. Graphify report

File: `graphify-out/GRAPH_REPORT.md`.

Recorded structural facts:

- Date: 2026-05-27.
- Corpus: 85 files, about 17,701 words.
- Graph: 873 nodes, 2911 edges, 54 communities.
- Extraction: 57 percent extracted, 43 percent inferred, 0 percent ambiguous.
- Inferred edges: 1254, average confidence 0.52.
- Built from commit: `d3ade89f`.
- Top connected nodes included `SQLiteUnifiedStore`, `ParsedChunk`, and `AccessTier`.

Important caveat: the report itself says inferred relationships need verification. This is useful architecture evidence, not a model/evaluation result.

### Encoding/Embedding Models Used

There are multiple embedding paths. They are not equivalent.

#### Parser QA script

Uses `HashingEmbeddingProvider(dimensions=32)`.

This is not a neural model. It:

- tokenizes identifiers/words,
- SHA256-hashes each token,
- maps the hash into vector buckets,
- assigns sign from the hash,
- L2-normalizes the vector.

#### `run_demo.py`

Uses `HashingEmbeddingProvider()` with default `dimensions=128`.

#### Production indexer and gateway bootstrap

Default is `LocalTransformersEmbeddingProvider` with:

- model name: `nomic-ai/nomic-embed-text-v1.5`
- local files only
- mean pooling over last hidden state
- L2 normalization

But this default requires the model to already exist locally. `CIS_EMBEDDING_BACKEND=hashing` switches production to `HashingEmbeddingProvider`.

#### UMMDB summarizer hook

`EmbeddingHook` also defaults to `nomic-ai/nomic-embed-text-v1.5`, local files only, with optional mock fallback.

This hook is tested but not the production indexer/gateway embedding implementation.

#### Reranker

`Reranker` can load:

- `cross-encoder/ms-marco-MiniLM-L-6-v2`

But gateway production prompt building uses `LexicalReranker`, not `Reranker`.

### Inference Model

Production inference is configured for llama.cpp, not a specific checked-in model.

Evidence:

- Gateway model hook defaults to engine id `llama.cpp`.
- Docker compose uses `ghcr.io/ggml-org/llama.cpp:server-cuda`.
- Model path must be supplied through `CIS_LLAMA_CPP_MODEL_PATH` or precision-specific model env vars.
- No GGUF model file is checked in.
- `run_demo.py` defaults to a deterministic local demo response unless `CIS_LOCAL_USE_LLAMA_CPP` is enabled.

## 9. What We Can Honestly Claim

Supported by code/tests:

- Python AST parsing produces interface and implementation chunks.
- Parser cascade falls back safely.
- File filtering rejects binary, excluded, sensitive, and secret-looking files.
- Indexing creates tiered artifacts and call/inheritance graph edges.
- SQLite retrieval enforces tier and repository scope.
- Query flow retrieves before inference.
- T1 users are prevented from seeing T3 implementation context in the tested flow.
- Cache keys include tier and scope.
- Concurrent identical queries are coalesced.
- Audit/history capture query outcomes.
- llama.cpp is integrated as a local streaming inference endpoint.
- Current test suite passes with 120 tests.

Not supported by checked-in evidence:

- A paper benchmark table.
- Results from real external repositories beyond the configurable QA script.
- A recorded run against Flask, Django, Requests, FastAPI, or any other external repository.
- A recorded learned-embedding benchmark.
- A recorded comparison of hashing embeddings vs Nomic embeddings.
- A recorded comparison of lexical reranking vs cross-encoder reranking.

## 10. The Most Important Architectural Boundaries

- `src/UMMDB` owns parsing, optional model hooks, and simple code graph helpers.
- `src/ingestion` owns converting parser output into persisted artifacts/edges.
- `src/retrieval` owns storage, embedding, search, reranking, and prompt assembly.
- `src/gateway` owns HTTP API, auth, scope, cache, rate limit, audit, history, and inference streaming.
- `src/inference` owns llama.cpp runtime/config helpers and request queue primitives.
- `docker-compose.yml` owns production process topology.
- `run_demo.py` owns local one-command demo behavior.

The main contract between core UMMDB and production is `ParsedChunk`. Everything else downstream is built around preserving or enforcing its fields: content, tier, fidelity, metadata, symbol, source span, kind, calls, and inheritance.
