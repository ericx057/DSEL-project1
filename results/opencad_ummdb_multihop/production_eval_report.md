# OpenCAD UMMDB Multihop Retrieval QA Production Evaluation

## Scope

This evaluation indexes the cloned OpenCAD repository through the existing UMMDB RepositoryIndexer, SQLiteUnifiedStore, HybridSearcher, and LexicalReranker path. No retrieval code or corpus files are modified by this harness.

## Corpus

- Repository: `https://github.com/nathan-sharp/OpenCAD.git`
- Commit: `89ebcba48ebb2f162b66702fc4797c9843ec5f64`
- Draft version: `0.1`
- Local path: `C:\Users\EXu\Documents\project1\external\OpenCAD`
- Files indexed: `25`
- Files skipped: `29`
- Artifacts indexed: `300`
- Edges indexed: `16`

## Question Design

- Question sets: `5`
- Questions per set: `50`
- Total questions: `250`
- Seeds: `104729, 104759, 104761, 104773, 104779`
- Every question has at least two gold evidence files.
- Gold evidence covers schema-example checks, assembly references, simulation/result links, validation scripts, and policy cross-references.

### Category Coverage

- `assembly-reference`: `40`
- `domain-schema`: `25`
- `example-schema`: `125`
- `policy-crossref`: `20`
- `result-buffer`: `5`
- `result-simulation`: `10`
- `simulation-target`: `5`
- `validation-process`: `5`
- `validation-schema-map`: `15`

## Retrieval Configuration

- `repository`: `opencad`
- `user_tier`: `3`
- `lambda_ratio`: `0.5`
- `vector_top_k`: `20`
- `graph_depth`: `3`
- `graph_breadth`: `50`
- `rerank_top_m`: `8`
- `embedding_dimensions`: `128`

## Retrieval Metrics

Accuracy@8 requires every gold evidence file for the question to appear in the top-8 reranked context. MRR@8 is the reciprocal rank of the first retrieved gold evidence file. Evidence file recall@8 is the mean fraction of gold evidence files present in the top-8 context.

- Accuracy@8, all gold files present: `0.9920`
- MRR@8, first relevant evidence file: `0.9533`
- Evidence file recall@8: `0.9960`
- Questions missing at least one gold file: `2`

### Retrieval By Category

| Category | N | Accuracy@8 | MRR@8 | Evidence Recall@8 |
| --- | ---: | ---: | ---: | ---: |
| `assembly-reference` | 40 | 1.0000 | 0.9875 | 1.0000 |
| `domain-schema` | 25 | 1.0000 | 0.9400 | 1.0000 |
| `example-schema` | 125 | 1.0000 | 1.0000 | 1.0000 |
| `policy-crossref` | 20 | 1.0000 | 0.8750 | 1.0000 |
| `result-buffer` | 5 | 1.0000 | 1.0000 | 1.0000 |
| `result-simulation` | 10 | 1.0000 | 1.0000 | 1.0000 |
| `simulation-target` | 5 | 0.8000 | 1.0000 | 0.9000 |
| `validation-process` | 5 | 1.0000 | 1.0000 | 1.0000 |
| `validation-schema-map` | 15 | 0.9333 | 0.5222 | 0.9667 |

## Answer Metrics

- Not scored yet. Use `model_input.jsonl` to collect model answers, then run the score command.

## Artifact Manifest

- Questions: `results\opencad_ummdb_multihop\questions.md`
- Gold: `results\opencad_ummdb_multihop\gold.jsonl`
- Retrieval results: `results\opencad_ummdb_multihop\retrieval_results.json`
- Model input: `results\opencad_ummdb_multihop\model_input.jsonl`
- Model scores: `results\opencad_ummdb_multihop\model_scores.json`

## Artifact Checksums

- Questions SHA256: `a026fad1daacee3fbd5cefdd901d1dbcecdad8f67c60e7916771d470168ffbd2`
- Gold SHA256: `b4c4190cb160ffa611c5e96ebb355dfb59c00963ea9f6491940abecec3e2dd5a`
- Retrieval results SHA256: `22b733ffa335a7702e09301d54b36fc5a9b5e69b3f41deaa9f66a9e02cee8f2b`
- Model input SHA256: `eeafa37095abd7fc4640c14366f7479eabf64bf4eb96ce235360dc2046e8908d`
- Model scores SHA256: `e3a78be3ad4f21f047a5641ea25448405ad7e8a9036a61f5131f1a5ee0e30e76`

## Production Notes

- The run uses T3 access to evaluate the full indexed corpus.
- The production query prompt includes the top 8 reranked chunks, so metrics are reported at 8.
- Accuracy is strict: every gold evidence file for a multihop question must appear in the retrieved prompt context.
- MRR is the reciprocal rank of the first retrieved gold evidence file in that top-8 context.
- The graph index includes parser-discovered code relationships plus structured JSON/schema/reference edges when the indexer can parse them.
- Binary payloads such as `examples/bracket_results_data.bin` are intentionally excluded by human-readable file heuristics.
