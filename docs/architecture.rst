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

That last boundary is worth being blunt about, because it is the one with a
deadline. How many options ``pssfmt`` *exposes* is reversible at any time.
Whether rules are *written against a style policy at all* is decided by the
first rule, and reversing it later means rewriting every rule module. So
rules ask per construct from the first day, even while every construct gets
the same answer.
