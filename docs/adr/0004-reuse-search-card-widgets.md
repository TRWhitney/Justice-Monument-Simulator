# ADR 0004: Reuse search card widgets

## Decision

Retain the existing QListWidget, OfferCard layouts, synchronous selection signals,
and main-thread Qt ownership. Update existing rows in place. Use Qt's delegate
`destroyEditor` hook to retain removed card widgets in hidden storage for reuse
when the result list grows again. The pool cannot exceed the largest result set
rendered at the current UI scale; changing scale discards it.

Wrapping correction, 2026-09-05: in-place rich-text changes settle through Qt
layout events after the synchronous row refresh. Coalesce card layout requests
and viewport resizes into a deferred sizing pass. Change item size hints only
when their dimensions differ, so measurement settles without a layout loop.
Retain synchronous selection and the existing widget pool. Initial Grumblo
rendering, reuse, selection, resizing, and scale changes must fit without a test
calling the sizing method to repair the display.

Refresh all offer-dependent labels, images, effects, and highlights when a card's
content changes. Cache only the most recent ranking inputs and results, including
the complete game state, candidate offers, utility weights, and simulated scores.
The visual row order and selection continue to come from the current search.

This removes repeated widget construction and unchanged ranking calculations
without introducing worker access to Qt widgets or partially populated results.
Initial construction, state-dependent formatting, and reattaching rows still run
on the GUI thread. This is a bounded optimization, not a guarantee of constant
latency for arbitrarily large custom datasets.

## Alternatives

Use the [configurable work comparison](search-rendering-options.html) to vary the
result-set sizes, compare allocation work, and export the selected option.

- Rebuilding every card repeats allocation, layout, and image work for unchanged
  rows. It is the previous behavior and the source of the measured search pauses.
- Updating rows and recycling removed cards preserves the current interaction
  behavior. Selected.
- Incremental rendering in timer batches bounds each construction burst, but
  requires additional behavior for selection and scrolling while rows arrive.
  Defer unless larger datasets justify that added lifecycle.
- A painted item delegate could avoid widget allocation, but would replace the
  established card renderer and duplicate its rich-text layout behavior. Defer.

## Verification

Compare reused cards with fresh renders across text, NPC, and effect queries,
changed state, images, and empty results. Check selection, scrolling, wrapping,
scale changes, and deferred deletion. Record direct GUI captures and local timing
measurements through an explicit verification run in ignored scratch storage.
