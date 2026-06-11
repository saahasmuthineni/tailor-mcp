# Vendored tiktoken vocabulary (cl100k_base)

The file `9b5ad71b2ce5302211f9c61530b329a4922fc6a4` is the canonical
OpenAI `cl100k_base.tiktoken` BPE vocabulary, vendored so that the
token-efficiency benchmark (`benchmarks/token_efficiency.py`) and its
receipt freshness guard (`tests/test_benchmark_receipt.py`) run fully
offline. Without it, tiktoken downloads the vocabulary from
`https://openaipublic.blob.core.windows.net/encodings/cl100k_base.tiktoken`
on first use — which would let a transient network failure to that
host hard-fail CI (the freshness guard deliberately does not skip;
see the test's docstring).

- **Filename** is tiktoken's own cache convention: the SHA-1 of the
  canonical source URL above
  (`sha1("https://openaipublic.blob.core.windows.net/encodings/cl100k_base.tiktoken")
  = 9b5ad71b2ce5302211f9c61530b329a4922fc6a4`). tiktoken finds it by
  pointing `TIKTOKEN_CACHE_DIR` at this directory; the benchmark
  script does that automatically (`os.environ.setdefault`, so an
  operator-set `TIKTOKEN_CACHE_DIR` still wins).
- **Integrity**: tiktoken itself verifies the file's SHA-256 on load
  against its pinned expected hash
  (`223921b76ee99bde995b7ff738513eef100fb51d18c93597a113bcffe865b2a7`).
  A corrupted or tampered file is rejected, not silently used.
- **Not shipped in the wheel** — `benchmarks/` is outside the
  packaged `src/tailor` tree, so the 1.7 MB vocabulary adds nothing
  to the install footprint.
