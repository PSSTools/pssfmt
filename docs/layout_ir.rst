The Layout IR
=============

.. note::

   **It is called the Layout IR, not the Doc.**

   Prettier's literature -- and most of the writing about Wadler-style pretty
   printing -- calls this structure a "Doc". In this project ``sphinx-pss``
   exists, ``docs/`` exists, and "Doc" is actively misleading. When reading
   that literature, read "Doc" for "Layout".

A rule does not decide where lines break. It describes the *shape* of a
construct -- what may break, what must break, what stays together, how much
things indent when they do -- and hands that description to the engine, which
picks a layout that fits the page. Separating the two is what keeps rules
small enough to be reviewable and keeps line-breaking bugs in one place.

The node set
------------

.. list-table::
   :header-rows: 1
   :widths: 18 82

   * - Node
     - Meaning
   * - ``Text``
     - Literal characters. Never contains a newline: a newline in the output
       is always a layout decision, never a payload.
   * - ``Concat``
     - Sequence.
   * - ``Group``
     - A break-together unit. Flat if its whole contents fit in the width
       remaining; otherwise every ``Line`` directly inside it becomes a
       newline.
   * - ``Indent``
     - Increase indentation by a column count, for a subtree.
   * - ``Align``
     - Indent to the *current column* plus an offset -- hanging alignment,
       where the target depends on where the line has got to.
   * - ``Line``
     - A space when flat, a newline when broken.
   * - ``SoftLine``
     - Nothing when flat, a newline when broken.
   * - ``HardLine``
     - Always a newline, and forces every enclosing group to break.
   * - ``Fill``
     - Greedy packing: as many items per line as fit.
   * - ``IfBreak``
     - Content chosen by the enclosing group's mode.
   * - ``Verbatim``
     - Byte-preserved text, exempt from width, forces enclosing breaks.
   * - ``BreakParent``
     - A marker with no output that forces enclosing groups broken.

A worked example
----------------

.. code-block:: python

   from pssfmt.layout import concat, group, indent, join, render, text, LINE, SOFTLINE

   items = join(concat(text(","), LINE), [text("addr"), text("data"), text("valid")])
   doc = group(concat(
       text("("),
       indent(concat(SOFTLINE, items), 4),
       SOFTLINE,
       text(")"),
   ))

At a width that fits, the group stays flat and the ``SoftLine``\ s vanish::

   (addr, data, valid)

At a narrower width it breaks, and every ``Line`` inside it breaks with it --
all together, not one at a time::

   (
       addr,
       data,
       valid
   )

All-or-nothing is the property that makes the output readable. A greedy
line-filler would produce ``(addr, data,`` / ``valid)``, which is where the
argument list happened to run out of room rather than anything about the
code.

Where ``Fill`` is right instead
-------------------------------

For an argument list, all-or-nothing is what you want. For a *homogeneous*
list -- one where no item means more than any other -- packing is better:

.. code-block:: python

   fill_with(concat(text(","), LINE), [text(r) for r in ranges])

::

   x in [0..7, 16, 32..63, 128..255,
         512, 1024..2047];

This matters more in PSS than in most languages: constraint range lists and
enum bodies are exactly this shape, and exploding them one item per line
wastes most of a screen.

``Fill`` measures the *pair* (item, separator, next item), not the item
alone. Measuring the item alone is the classic off-by-one -- it packs an item
onto the line, then finds that the separator which must follow does not fit,
and overflows by exactly the separator's width.

How the engine chooses
----------------------

Two passes.

**Break propagation** walks bottom-up and marks every group containing a
forced break -- a ``HardLine``, a ``BreakParent``, a ``Verbatim``, or an
already-broken group -- as broken. It runs first, for the reason in
:doc:`architecture`.

One exception, and it is deliberate: propagation does not descend into an
``IfBreak``'s branches. A forced break inside ``break_contents`` must not
make its own condition true, or the node would be self-fulfilling and
therefore useless.

**Layout** walks top-down with an explicit command stack. At each group it
asks ``fits``: laid out flat, does this group -- *plus everything that must
still follow it on this line* -- stay inside the width remaining?

That second clause is the part naive implementations drop. A group that fits
in isolation but is followed by ``);`` on the same line does not fit. ``fits``
therefore continues into the enclosing command stack after exhausting the
group, and stops at the first newline it reaches, because everything past
that newline is somebody else's line.

Both walks are iterative rather than recursive. Deeply nested activities and
long expression chains both produce trees deeper than is comfortable for
recursion, and a formatter that raises ``RecursionError`` on a large file is
a formatter nobody leaves in a pre-commit hook.

Measuring width
---------------

Width is display columns, not characters: East-Asian Wide and Fullwidth forms
count as two, combining marks as zero. It lives in exactly one function,
:func:`pssfmt.layout.width_of`, so the decision is one call site rather than
a policy scattered through the engine.

Column alignment
----------------

Alignment is a separate pass over the engine's finished output. A rule marks
a column stop with a zero-width sentinel and leaves the author's original
spacing after it; the pass gathers runs of lines that align together and
resolves each run in one of four modes:

``align``
    Pad each column to the widest cell in its group.
``flush-left``
    One space at each stop.
``preserve``
    Leave the author's spacing exactly as it was.
``infer`` *(default)*
    Per group: if the author already had this block aligned, align it;
    otherwise flush it left.

``infer`` is why the usual argument about alignment is a false choice. The
case against alignment is that adding one line reflows a whole block, so a
one-line change shows up as a twenty-line diff. The case for it is that
hand-aligned register tables are genuinely more readable, and PSS codebases
have them. ``infer`` gives each block whichever answer its author already
chose -- alignment becomes opt-in per block, in the code, with no
configuration on either side.

Carrying the author's original spacing *after* the marker is what makes this
implementable at all. By the time this pass runs the source is gone, and the
only record of what the author did is what the rule brought along.

Two rules keep it safe:

* **Alignment never causes an overflow.** If aligning a group would push a
  line past the column limit, the group falls back to flush-left. (A line
  that is over the limit flush-left too is over the limit either way, and
  flattening the block for it would lose the alignment without fixing
  anything -- so that case keeps its alignment.)
* **An indentation change always ends a group.** Members at different nesting
  depths are not one table, and aligning across depths produces the drifting
  columns that make people turn alignment off entirely.
