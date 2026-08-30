# pssfmt

A formatter for the Accellera Portable Test and Stimulus Standard.

```console
$ pip install pssfmt
$ pssfmt -i src/pss/          # rewrite in place
$ pssfmt --check src/pss/     # exit 1 if anything would change
```

## What it promises

The safety contract is the reason a team is willing to put a formatter in a
pre-commit hook, and most formatters never write it down:

- **It does not change your code.** Output re-lexes to the same token sequence
  as the input — same types, same text — and comment text is preserved
  character for character.
- **It converges.** Formatting formatted code is a no-op.
- **It fails safe.** If either property is violated for a file, `pssfmt` emits
  that file *unchanged* with a diagnostic. A formatter that is occasionally a
  no-op is survivable; one that occasionally corrupts is not.

The first two are enforced over the whole shared PSS test corpus: 92 files, of
which 64 are already byte-identical to what `pssfmt` would write, 28 are
reformatted, and none trip the fail-safe. Every one is idempotent.

## What it formats

Declarations and their bodies and headers, `extend` blocks, `import`
statements, field declarations, expressions, constraints, activities, template
arguments, `enum` declarations, function prototypes and bodies, the statements
inside them, `match`, and `exec` bodies.

Everything else is reproduced exactly as you wrote it. That is the design
rather than a stage of it: a construct with no rule falls back to the formatter
that changes nothing, so an incomplete rule set cannot corrupt a file, and
adding a rule cannot make an unrelated construct worse. `docs/status.rst` lists
what is left and why each one is waiting on a decision rather than on code.

The canonical style is *measured*, not preferred — each rule is derived from
counts over that corpus, and `docs/style.rst` shows the count behind each one.

## Escape hatches

```pss
// pssfmt off
bit[8]   addr;      // hand-aligned, and staying that way
bit[32]  data;
// pssfmt on
```

Plus `// pssfmt ignore` for a single construct and a `.pssfmtignore` file for
whole paths. A formatter without an off-switch is not adopted in a codebase
with hand-aligned register tables, and PSS codebases have those.

## Documentation

`docs/` — built with Sphinx, and the build is a test rather than a courtesy.

- **Using it** — quickstart, the CLI, configuration, the style and its
  measurements, and project status
- **Developing it** — the pipeline architecture and the layout-engine reference

The layout engine (`src/pssfmt/layout/`) is a Wadler-style pretty printer: the
Layout IR, break propagation, `fits`/`best` line breaking, greedy `Fill`, and a
post-layout column alignment pass. It imports nothing — not `pssfmt`, not
`pssparser` — and a test enforces that rather than a convention, which is what
let it be built before the PSS front end existed and keeps it extractable.

## Building from source

```console
$ ivpm update                                   # resolves the dev dependency set
$ ./packages/python/bin/pip install -e . --no-deps
$ ./packages/python/bin/python -m pytest
$ make -C docs html
```

`ivpm` installs the dependencies into `packages/python`; the editable install
is what puts `pssfmt` itself on the path.
