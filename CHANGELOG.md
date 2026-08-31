# Changelog

Version numbers are ordinary semantic versions of the *tool*. The one thing
worth knowing before reading them: **a change to a default is a breaking
change** and advances the major component, because a formatter that quietly
reformats a pinned codebase on upgrade is a formatter organizations pin and
never upgrade again.

## 0.1.0 — first public release

`pssfmt` formats Accellera PSS source. This is an alpha in the sense the
classifier means: the pipeline is complete end to end and carries a checked
safety contract, but the rule set is deliberately partial and constructs are
still being added.

### The safety contract

This is the part worth reading before the feature list, because it is what the
tool is actually built around.

- **Three checks run on every format, and failing any one returns the input
  unchanged** with a diagnostic. The fail-safe is the default path, not a flag
  somebody can forget to pass: token equivalence (re-lex the output; every
  non-trivia token identical in type and text, comment text identical modulo
  trailing whitespace), idempotence (`fmt(fmt(x)) == fmt(x)`), and no new
  parse errors.
- **The parse-error check counts the parser's syntax errors, never the
  lexer's.** An unterminated `/*` lexes as `/`, `*`, identifier with the lexer
  reporting zero errors, so a lexer-based check would let a spacing rule turn
  `/*` into `/ *` and comment out the rest of a file. The parser sees it.
- **A construct with no rule is emitted verbatim**, not approximated. Partial
  coverage costs you unformatted code, never damaged code.
- Verified on 92 curated PSS files plus 4 standard-library packages: every one
  round-trips byte for byte through the null formatter, and every one that
  formats is idempotent and token-equivalent.

### Formatting

Declarations, headers, `extend` blocks, imports, field declarations,
expressions, constraints, activities, template arguments, function headers and
bodies, enumerations, and procedural statements. Comments are attached and
preserved. Hand-built aligned tables are recognized and preserved rather than
collapsed, and the formatter never inserts or removes a parenthesis.

### Command line

- `pssfmt FILE...` — format to stdout; directories are searched for `*.pss`.
- `-i` / `--in-place` — rewrite in place, via write-temp-and-rename, so an
  interrupted run cannot leave a truncated file.
- `--check` — write nothing; exit 1 if any file would change. Exit codes are
  0 formatted-or-already-clean, 1 `--check` would change something, 2 something
  went wrong. `1` means *"the answer is no"* and never *"I could not compute
  the answer"* — a broken `.pssfmt` exits 2, not 1, because a CI job must not
  report a missing dependency as a style failure.
- `--diff` — unified diff of what would change.
- `--lines A:B` — format only part of one file, repeatable. Whatever the
  selection, every edit is whitespace-only.
- `--explain` / `--explain-tree` — describe how the output was produced,
  including the Layout IR.
- `-q`, `--version`, and stdin/stdout with no `FILE` or with `-`.

### Configuration

`.pssfmt` or `[tool.pssfmt]` in `pyproject.toml`, discovered by walking up
from each file. `print_width`, `indent_width`, `continuation_indent`,
`use_tabs`, `brace_style`, `max_blank_lines`, `insert_final_newline`,
`line_ending`, `alignment`, `alignment_group_boundary`, and per-construct
overrides for indent, continuation, braces, alignment, boundaries, breaking
and spacing.

`.pssfmtignore` files are honoured with gitignore semantics. `// pssfmt off`
and `// pssfmt on` switch the formatter off within a file; the directive must
be the whole comment, so prose *about* the tool is not mistaken for a
directive.

The defaults were measured rather than chosen, by a survey tool that ships in
the repository so the next argument is settled by rerunning a command: 4-space
indent (251 of 255 steps), never tabs (0 of 4856 lines), K&R braces (732 of
733), `print_width = 80` — where the corpus does not merely average below 80
but stops there, 78 lines of length 80 against 19 of length 81. Two rules came
back split, and both split humans against a code generator; both were decided
for the humans.

### Known limitations

- The rule set is partial by design. Constructs without a rule pass through
  verbatim, so a file may format only in part.
- Five valid-PSS constructs are not yet reachable because of upstream grammar
  and lexer gaps: `action` in a package, `dist` constraints, `cover` in an
  activity, `_` separators inside based numbers, and octal escapes in string
  literals. Affected files hit the fail-safe and are left unmodified. These are
  tracked as `xfail` reproducers so a fix upstream cannot land unnoticed.
- Comment reflow is off, deliberately.
- `brace_style = "break"` (Allman) is recognized but not implemented, and says
  so rather than silently doing something else.

### Requires

Python 3.9 or newer — tested in CI on 3.9, 3.10, 3.11, 3.12 and 3.13 — and
`pssparser>=3.0.6`, which supplies the lossless token stream and concrete
syntax tree the whole design rests on. `tomli` is pulled in on 3.9 and 3.10
only, where `tomllib` is not yet stdlib.
