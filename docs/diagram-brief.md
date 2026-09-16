# Diagram brief: where the unpredictable part sits

A brief for one diagram, precise enough to hand to a designer or an image
tool. `scripts/make_brand_images.py` builds a working version as
`docs/assets/where-retrieval-sits.png`; this file is the specification it
implements, and the place to argue with it.

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

Three questions sit inside it, and none can be answered from outside:

1. Does the model call `Read` on the decision at all?
2. Once the text is in the context window, does attention land on it?
3. Do those tokens change the ones it emits?

Label the band: *sampled. No log of attention.*

The line that does the work, placed inside the zone:

> A transcript shows that a file was opened. It never shows that the file was
> used.

### Zone 3, the check (bottom)

Draw the gate **outside** Zone 2, reading from Zone 1. This placement is the
entire point, so make the arrow unmistakable: it goes to the transcript, and
never into the model.

The gate asks one question, which should appear as text:

> Does the transcript contain a read of every decision that governs this path,
> earlier in this session?

Two outcomes: **allow**, and **refuse** with the files to read named.

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
