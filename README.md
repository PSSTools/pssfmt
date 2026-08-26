# pssfmt

A formatter for the Accellera Portable Test and Stimulus Standard.

> **Pre-alpha.** `pssfmt` cannot format a file yet. The layout engine is built
> and tested; the PSS front end is not, because the token and CST API it needs
> does not exist in `pssparser` yet. See [`PLAN.md`](PLAN.md), Phase U.

## What is built

- **The layout engine** (`src/pssfmt/layout/`) — a Wadler-style pretty
  printer: the Layout IR, break propagation, `fits`/`best` line breaking,
  greedy `Fill`, and a post-layout column alignment pass with `align`,
  `flush-left`, `preserve` and `infer` modes.

  It imports nothing — not `pssfmt`, not `pssparser` — and a test enforces
  that rather than a convention. That is what let it be built while the
  upstream API is still in flight, and it keeps the engine extractable.

## What is next

The critical path is upstream, in `pssparser`: a lex-without-parse token
stream over all channels, a parse-only CST entry point, and Cython bindings
for both. Then the null round-trip formatter — the proof that the pipeline is
lossless — and only then any style opinion at all.

`PLAN.md` tracks every item, and the eight open decisions that gate them.

## Getting started

```console
$ ivpm update                              # resolves the dev dependency set
$ ./packages/python/bin/python -m pytest
$ make -C docs html
```

## Design

- [`formatter.md`](formatter.md) — the design of record
- [`PLAN.md`](PLAN.md) — implementation, test and documentation plan
- `docs/` — Sphinx documentation, including the layout-engine reference
