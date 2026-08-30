Architecture
============

The pipeline
------------

.. code-block:: text

   source bytes
        |
        v
   [ lexer ]  ---- all channels: code (0), WS (10), // (11), /* */ (12)
        |
        +--> token stream ---> [ trivia map ] ---- comments attached to CST nodes
        |                                             leading / trailing / dangling
        v
   [ parser ] ---> CST  ------> [ rules ] --------> Layout IR
                                    ^                   |
                                    |                   v
                             resolved Style       [ layout engine ]
                            (per construct)        fits / best / breaks
                                                        |
                                                        v
                                                 [ alignment pass ]
                                                        |
                                                        v
                                                 [ verifier ] --- token equivalence
                                                        |          idempotence
                                                        v          no new parse errors
                                                     output
                                                   (or, on failure,
                                                    the input unchanged)

Two orderings in that diagram are load-bearing and easy to get wrong.

**Break propagation runs before layout.** A group containing an unconditional
newline must be known to be broken *before* anything measures it, or the
measurement treats the newline as zero width, decides the group fits, and
produces a flat line with a newline in the middle of it.

**Alignment runs after line breaking.** Column alignment changes how wide a
line is; line breaking decides where lines end based on how wide they are.
Running them in the other order makes them mutually recursive, with no
fixpoint guarantee. Running alignment last means it can never influence a fit
decision, and the cost is that alignment must live within the lines breaking
already chose.

Why the CST, and not the AST
----------------------------

This proposal recurs -- roughly annually, in every formatter project -- so the
argument belongs somewhere durable.

``pssparser``'s AST is a good AST, which is exactly why it is the wrong input
for a formatter. It has already discarded things a formatter needs:

* **``compile if`` branches.** The AST keeps the branch the conditions
  selected. A formatter must format *both*, and must never evaluate the
  condition -- reformatting a file must not depend on which build
  configuration you happen to be in.
* **Authored parentheses.** ``(a + b) * c`` and ``a + b * c`` differ in the
  CST and can be identical in the AST. A formatter that loses redundant
  parens changes code that people deliberately wrote for readability; one
  that cannot tell which parens were authored has to guess.
* **Precise expression locations.** Without them the formatter cannot map its
  output back to the source it came from, which is what ``--lines``, range
  formatting, and minimal edits are all built on.

The asymmetry is the real argument. **CST losslessness is structural**: the
CST plus the full token stream *is* the file, so it is proven once and stays
proven. **AST losslessness is a permanent obligation**: every future AST
change has to be checked against the formatter's needs, by someone who
remembers that the formatter has needs. The first has a fixed cost; the
second has an unbounded one.

The layer boundaries
--------------------

``src/pssfmt/layout/``
    The Layout IR and the engine. Imports nothing from ``pssfmt`` and nothing
    from ``pssparser`` -- enforced by a test, not by convention. Two things
    depend on that: the engine could be built and tested while the upstream
    token API was still unwritten, and it stays extractable as a standalone
    pretty-printer.

``src/pssfmt/rules/``
    The PSS style opinion, and the *only* place style lives. A rule turns one
    CST construct into Layout IR. It never reads configuration and never
    writes a spacing constant; it asks a resolved ``Style`` object, per
    construct.

``src/pssfmt/style.py``
    The seam between the two. The one module that knows a default.

``src/pssfmt/config.py`` and ``src/pssfmt/ignore.py``
    *How* to format and *what* to format, kept apart because they resolve by
    opposite rules and each rule is wrong for the other. Configuration stops
    at the first file found; ignore files stack from the repository root down.

    A configuration is a set of **values**, and merging values makes "which
    file set this?" unanswerable by reading -- so the chain is not merged, and
    composing two files is a separate, explicit feature. An ignore file is a
    set of **rules**, which compose by construction: ``!`` exists precisely so
    an inner file can overrule an outer one, and refusing to stack them would
    make a subdirectory's ignore file silently disable the repository's.

    Exposing an option is where those two modules meet the rest of the
    pipeline, and it carries an obligation worth stating architecturally: **a
    key the configuration accepts is a promise, so the last step before
    exposing one is finding the code that keeps it.** Two of the twelve keys
    had no such code when the config layer was written -- one was made real,
    one is refused -- and a test asserts of every remaining key that setting
    it changes real formatter output. The alternative is not a missing
    feature, it is a tool that accepts an intention and then disagrees with
    it silently, which is strictly worse than not offering the option.

``src/pssfmt/ranges.py``
    Formatting *part* of a file. The whole file is always formatted -- a line
    range is not a syntactic unit, so it has no tree, and the indentation it
    should get is a fact about ancestors outside it -- and this module decides
    how much of the result to keep.

    Which means the output has to be cuttable at a line boundary without
    cutting through a token, and that is where the design was decided by a
    measurement rather than by an argument. The obvious implementation asks
    ``difflib`` for hunks and keeps the overlapping ones; over 92 corpus files
    at 24 styles, **5768 of 11400 such hunks are not whitespace-only**.
    ``difflib`` matches lines, and every closing brace on its own line is the
    same line, so when the line count shifts it pairs one with another and the
    surrounding hunks straddle real code.

    So the cut points are computed instead. Because the formatter preserves
    tokens, the file with all whitespace removed is invariant; number each
    line boundary by how much of that text precedes it, and boundaries with
    equal numbers are places where both sides have emitted the same thing so
    far. Cutting there is safe and cutting elsewhere is not.

    The lesson is the one this project keeps relearning from the other side.
    "The architecture guarantees it" was true -- token preservation is a
    whole-file property and it holds -- and the guarantee still did not
    survive being cut up by a tool that does not know what a token is. **A
    property of an artifact is not automatically a property of its pieces**,
    and the way to find that out is to count, not to reason.

``src/pssfmt/verbatim.py``
    What the formatter *copies* rather than composes. Small, and load-bearing
    for a reason worth stating: every claim the tool makes about its own
    output -- the style properties, and later ``--check`` and ``--diff`` -- is
    a claim about gaps it decided, and a target-template ``exec`` body has
    none. Three corpus gates were quietly making those claims about foreign
    text and passing only because no corpus file contained an untidy one.

    It answers the question in both directions, and the two are separate
    passes on purpose. Which output *lines* were copied is asked after
    formatting, by anything checking the result. Which input *tokens* must not
    be composed is asked before it, and that is where the ``// pssfmt off``
    directives resolve to. Putting them in one module is not tidiness: a
    region the author switched the formatter off over is also a region the
    style properties cannot be asserted over, and keeping the two answers
    apart is how the second one gets forgotten.

A rule that writes tokens out, rather than moving the author's text around,
declares the token types it expects and **declines anything else**. That is
worth stating as an architectural rule and not an implementation detail,
because it is what bounds the blast radius of a rule set that will be
incomplete for a long time: there is no global mapping from a character to a
spacing decision, so a rule cannot quietly mis-format a construct nobody
wrote it for. The same character is genuinely different rules in different
places -- ``*`` is multiplication in an expression and a wildcard in
``import pkg::*`` -- and a table that had to choose between them would be
wrong somewhere by construction.

Declaring the token types is necessary and it is not sufficient, because some
tokens have no answer *at that granularity*. ``-`` is unary or binary and
``(`` is a call, a grouping or a cast, and a map keyed on the token type has
one slot for each. The rule is that where a token's meaning is a fact about
the **tree**, the site comes from the tree: the PSS grammar already names
``unary_op`` and ``add_sub_op`` separately, so a rule that has walked the
parse hands the emitter a per-token answer rather than letting it infer one.
The emitter still never guesses -- what changes is only who is asked.

A rule doing that owes itself a completeness check, and the reason is a
general one worth carrying to the next such case. Falling back to the token
type for a position the walk missed is *worse* than declining: an ambiguous
type's entry is a placeholder, so the output is wrong rather than absent, and
nothing about it says so. Any token type whose site comes from the tree is
therefore enumerated, and an unclassified one refuses the whole span.

Underneath every spacing decision sits a floor the style cannot lower: two
tokens must never be emitted in a way that lexes as one. That is a question
about the lexer rather than about taste, and it is kept separate from the
style for that reason. It is also the one place where a closed vocabulary
stopped being enough: as long as no rule emitted operators, no two tokens in
any vocabulary could merge, and the floor only had to know about identifiers.
Expressions ended that -- ``a & &b`` written tight is ``a && b``, a different
program that parses -- so the floor is now maximal munch stated directly, and
it is verified against the real lexer over every ordered pair of lexemes
rather than against a hand-written list of hazards.

Stating the floor correctly turned out to be the easier half. The harder half
is that a floor is only a floor if **every** place two tokens are written next
to each other consults it, and the token emitter is not the only such place: a
declaration header is composed against its ``{``, and a declaration against a
stray ``;``, as layout rather than as a span of tokens. Both were written long
before the floor had anything to say to them, and both were missing it -- one
visible only under a non-default spacing, the other reachable at the default
by any file with a syntax error in it. The fail-safe meant neither could
corrupt anything; the symptom was a correct file silently declining to format.

The lesson generalises past this floor, to any invariant that a helper
enforces rather than the type system: *the way to audit it is to enumerate the
call sites, not to re-read the rule.* Re-reading the rule confirms the rule,
which was never the thing that was wrong.

The same shape appeared once more, at the other end of the pipeline, and it is
worth recording because the second instance is where a pattern becomes
something to look for. Everything a formatter emits is composed -- a rule
asked for a gap, the engine chose a break, the alignment pass moved a column
-- except the file's tail. Trivia after the last code token belongs to no CST
node, so no builder can emit it and the pipeline appends it verbatim. That is
the right default, since dropping it truncates the file. It also meant every
*file-level* property was true of every line but the last one: a CRLF file
came back mixed, trailing whitespace survived where the engine strips it
everywhere else, and trailing blank lines outlived the limit that clamps them
in the middle of a file. Two of the three were declared style options that
nothing read.

So the general form is: **an invariant is audited by enumerating the places
output is produced, and "the text a rule emitted" is never the only one.**
Copied text is exactly where properties go to fail, because it arrives without
having been asked any of the questions the composed text was asked.

Line endings then have to be handled in one specific direction, which is worth
stating because the obvious alternative fails for a non-obvious reason. They
are normalised on the way *in* and applied on the way *out*, so no rule, no
width measurement and no check ever sees a ``\r``. Converting on the way out
alone does not work: a multi-line ``/* */`` comment and a triple-quoted
``exec`` template are each a *single token* whose text spans lines, so
substituting over finished output edits token text -- and the verifier,
correctly on the evidence available to it, calls that corruption. The
verifier grants exactly one exemption in return, and its bound is worth being
precise about: token text is compared with line endings normalised, permitting
``\r\n`` and ``\n`` to stand for each other and nothing else, anywhere. That
conversion is byte-level, total, and its own inverse -- checkable without a
parser, which is why it is allowed to happen outside the part a parser checks.

A rule set that is incomplete on purpose has one failure mode that its own
tests cannot see, and it is worth naming because it took a while to find. A
rule can only run on a node whose ancestors all have rules, so **an unwritten
rule high in the tree hides every defect below it**. ``extend`` is the
worked example: 31 of the 92 corpus files put their declarations inside one,
and until ``extend`` had a rule, every rule that would have applied within
those files was inert. The field rules had been flattening hand-built
alignment tables in eight of them for two releases -- reachable by any user
who did not happen to use ``extend``, and invisible to a corpus gate that
compares whole files.

The lesson is not "write more rules". It is that *coverage of the corpus text*
and *coverage of the rules that ran* are different measurements, and only the
second one finds this. Counting how often each builder is actually reached is
now part of finishing a rule module, and a builder that the corpus never
reaches is treated as untested however green the suite is.

That measurement is now a test rather than a habit. It instruments the rule
registry, formats the corpus, and pins the set of builders no corpus file
reaches -- as an equality, so a construct *gaining* corpus coverage fails too,
because the comment claiming it had none has stopped being true. Two builders
are in that set today, and each names where it is covered instead. The
distinction it keeps alive is the one that took two releases to learn: being
reached by a hand-written example and being reached by PSS somebody wrote are
different facts, and only the second supports a claim that begins "measured
across 92 files".

The measurement earned itself back on the next module. Template arguments are
137 lists across 34 files, every test passes and the corpus is quiet -- and
13 of the 137 are never reached, because they sit inside ``exec`` bodies and
function parameter lists, neither of which has a rule. Nothing in a green
suite says so. The difference from ``extend`` is only that this was known
before shipping rather than after, which is the whole point of measuring it.

That last boundary is worth being blunt about, because it is the one with a
deadline. How many options ``pssfmt`` *exposes* is reversible at any time.
Whether rules are *written against a style policy at all* is decided by the
first rule, and reversing it later means rewriting every rule module. So
rules ask per construct from the first day, even while every construct gets
the same answer.
