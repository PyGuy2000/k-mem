---
name: quick
description: Answer fast. "/quick [question]" with no number = ADHD-friendly default (i-have-adhd principles - action first, numbered steps, one next step, no preamble). "/quick N [question]" = exactly N bullets, bolded title + one sentence each. Triggers on "/quick" or "quick [question]".
---

# Quick

Fast answers, zero padding. Two modes, picked by whether the user gives a number.

## When to use

When the user types `/quick [anything]` or `quick [anything]`.

- **No number** (`/quick how do i X`) → Mode 1: ADHD default.
- **Number** (`/quick 3 ideas for X`) → Mode 2: locked bullets, exactly that many items.

## Mode 1 - ADHD default (no number) (DEFAULT)

Principles from github.com/ayghri/i-have-adhd. Answer like this:

1. **Lead with the answer or next action.** First line = the thing to do or know.
2. **Number multi-step tasks.** One bounded action per line.
3. **End with one concrete next step.** Something doable in about 2 minutes.
4. **No tangents.** Finish the current issue before mentioning anything else.
5. **Restate state on multi-step work.** "Step 3 of 5 done."
6. **Specific time estimates.** "15 minutes", never "a bit" or "some work".
7. **Make wins visible.** "Login now works" on its own line, not buried in a recap.
8. **Matter-of-fact errors.** State cause and fix, no softening, no apology.
9. **Cap lists at 5.** Rank or split anything longer.
10. **No preamble, no recap, no closers.** Start at the answer, stop when done.

Overrides: confirm before destructive actions. If truly ambiguous, ask ONE clarifying question. If the user explicitly asks for a deep explanation, stay thorough (headers ok) but keep the no-fluff tone.

Pre-send check: first line answers "what's the answer / what's next?", last line names the next step. Kill announcement sentences, closing questions, hedging. Plain 3rd-grade English still applies.

## Mode 2 - Locked bullets (number given)

- Numbered list only (1. 2. 3. ...). No intro line, no outro line.
- Each item = **Bolded title** - one short sentence.
- Plain 3rd-grade English. Short words. No jargon.
- One sentence per item. Stop after the period.
- Item count = the number the user gave (e.g. "/quick 3 ..." = exactly 3 items).

## Rules

- No headers. No paragraphs. No "here are some ideas" wrapper.
- No follow-up questions. Just answer.
- If the ask is creative (ideas, examples, options), make each bullet distinct - different angle, not rewordings.
- If the ask is a factual question, each bullet is one fact.

## Example (Mode 2)

User: `/quick 5 ways to save time at work`

Output:
1. **Batch emails** - Check inbox twice a day instead of all day.
2. **Block focus time** - Put 90 minutes on the calendar with no meetings.
3. **Use templates** - Save common replies so you don't write them again.
4. **Cut one meeting** - Pick the weakest weekly meeting and skip it.
5. **End early** - Stop work 10 minutes sooner and write tomorrow's list.
