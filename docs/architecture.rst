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
