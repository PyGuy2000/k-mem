# Diagram brief: where the unpredictable part sits

A brief for the two diagrams in the README, precise enough to hand to a
designer or an image tool. `scripts/make_brand_images.py` builds working
versions as `docs/assets/the-fallacy.png` and `docs/assets/the-system.png`;
this file is the specification they implement, and the place to argue with it.

## The claim the diagram must make

One sentence, and every element should serve it:

> The model's use of a file is sampled and unobservable. The record of a tool
> call is a fact on disk. K-mem puts the check on the fact.

Two things the diagram must **not** say, because both are false:

- That K-mem makes the model deterministic. It does not touch the model.
- That K-mem verifies comprehension. It verifies that a read event happened
  before a write was attempted. Nothing more.

## Three zones

The whole design is one boundary drawn in the right place.

### Zone 1, deterministic (top band)

Everything here happens the same way every time, and leaves an artifact.

- **Files on disk.** The decision records, `STATE.md`, `.claude/adr_map.json`.
- **Hooks.** SessionStart injects the brief and the inventory. PreToolUse fires
  on every write. These run whether the model wants them or not.
- **The transcript.** Every tool call the session made, in order, with its
  input. Written by the harness.

Label the band: *runs the same way every time, and leaves a record.*

### Zone 2, probabilistic (middle band, visually distinct)

This is the carved-out region. It should look different: dashed border, warm
colour, no hard edges.

Locate the steps inside one turn, in order, so the reader sees where in the
loop this happens:

```
context window  ->  1. does it call Read?  ->  2. attention, then tokens  ->  the edit
```

The boundary encloses steps 1 and 2 only. The context window sits outside it
on the left, because a hook put the file there and that is certain. The edit
sits outside it on the right, because it arrives either way.

Each step carries its record status, and they differ:

| Step | Record |
|---|---|
| 1. the tool-call decision | a `tool_use` line lands in the transcript. Nothing reads it. **Recorded, unchecked.** |
| 2. attention, then tokens | attention leaves no log. Nothing to check, even in principle. **Not recorded.** |

That difference is why one closes and the other does not.

Label the band: *sampled. No log of attention.*

The line that does the work, placed inside the zone:

> A transcript shows that a file was opened. It never shows that the file was
> used.

### Zone 3, the check (bottom)

Draw the gate **outside** Zone 2, reading from Zone 1. This placement is the
entire point, so make the arrow unmistakable: it goes to the transcript, and
never into the model. Mark the line it does not cross.

An earlier version stated the two unverifiable steps as text and drew no
boundary and no gate. It described the problem and never showed the answer.
Both placements have to be in the picture: the boundary around the two steps,
and the check on the far side of it.

The gate asks one question, which should appear as text:

> Does the transcript contain a read of every decision that governs this path,
> earlier in this session?

Two outcomes: **allow**, and **refuse** with the files to read named.

## Marking what this project contributes

Half the diagram is machinery that exists whether or not anyone installs this.
Leaving that unmarked lets the picture read as "here is how the world works",
which hides the contribution and overstates it at the same time.

So a small cyan `k-mem` tag sits on exactly three things:

| Tagged | Why |
|---|---|
| `.claude/adr_map.json` | the one file k-mem asks you to add |
| the hooks that ship with it | the read gate, the sweep, the session brief |
| the gate | the check itself |

Everything else stays plain: the model, the transcript, the hook mechanism the
harness provides, and the decision records you write anyway. The legend says so
in one line.

Placement rule: a tag closes a phrase, never splits one. A tag in the middle of
a sentence reads as a footnote marker and breaks the line.

This carries a claim worth making. K-mem is small. It adds one map file and a
set of hooks that read artifacts already lying around. It builds no store and
touches no model.

## What crosses each boundary

Four arrows, no more:

| From | To | Label |
|---|---|---|
| Files | Model | injected at session start, always |
| Model | Files | a `Read` call, if it makes one |
| Model | Gate | proposes a write |
| Transcript | Gate | the recorded fact the gate reads |

The second arrow is the one to draw as uncertain: dashed, or with a question
mark. Whether it happens is the thing nobody controls.

## Reading order

Left to right is wrong here. The story is vertical:

1. Files go in.
2. Something unobservable happens.
3. A write is proposed.
4. The gate checks the record and answers.

## Style

Brand colours, from the site tokens:

| Use | Hex |
|---|---|
| Background | `#080C16` |
| Deterministic zone, the gate | `#00E1FF` |
| Probabilistic zone | `#FF941A` |
| Body text | `#F1F5F9` |
| Secondary text | `#94A3B8` |
| Allow | `#4ADE80` |
| Refuse | `#F87171` |

No icons of robots or brains. No cloud shapes. The model is a box like any
other, which is the point: it is one component in a loop, and the loop is
what the diagram is about.

## The caption

Under the image, wherever it appears:

> The gate makes no judgement about whether the model understood the decision.
> It checks whether the decision was opened before the edit was attempted, and
> that is a fact the transcript records.

## Common ways this goes wrong

- **Drawing retrieval as a database lookup.** There is no vector store and no
  similarity search in this loop. Retrieval here is the model choosing to call
  a read tool, and the harness returning the bytes.
- **Putting the gate inside the model's box.** Then it is subject to the same
  sampling it exists to bound, which is the failure the whole project is about.
- **Implying the refusal is permanent.** Reading the decisions and re-issuing
  the identical edit passes. The gate delays a write; it does not forbid one.
- **Making Zone 2 look broken.** It is not a defect. It is the part that
  cannot be verified from outside, drawn so the boundary is visible.
