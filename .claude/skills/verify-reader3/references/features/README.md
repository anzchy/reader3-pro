# Feature Map

One file per ledger row (`docs/feature-ledger.md`, `F-NNN`), saying how to prove that row's
Confirm step in the running app with control.py and `$B`. Read the row's file before you
start; [`../../SKILL.md`](../../SKILL.md) has the stages, helpers and general gotchas.

| File | Ledger row | Status |
|---|---|---|
| [F-009.md](F-009.md) | Paginated epub.js reader | accepted |
| [F-011.md](F-011.md) | Keyword search | accepted |
| [F-013.md](F-013.md) | AI Q&A + summary | accepted |
| [F-018.md](F-018.md) | Annotations + notes | partial |
| [F-020.md](F-020.md) | Settings page + API | accepted |

Rows without a file are not mapped yet. Rows whose ledger status is `absent` never get one.

## The four-H2 rule

Every map file is named `F-NNN.md` and:

1. starts with an H1 whose first word is its id, e.g. `# F-018 Annotations + notes`;
2. links its ledger row as `[F-NNN](../../../../../docs/feature-ledger.md)`, and that is the
   first link to the ledger in the file;
3. has exactly these four H2 sections, in this order, and no others:
   - `Sub-features`: the row's claims, one bullet each, paraphrased from the ledger;
   - `How to get to it (user POV)`: the clicks a user makes, from the library page;
   - `Driving it with control.py and $B`: the commands, each control.py line on one line
     (no `\` continuations), using only flags that exist;
   - `Gotchas`: where the ledger Confirm text and the sandbox disagree, and what to do.

Every file must also be listed in this README. After any edit, run:

```bash
python3 .claude/skills/verify-reader3/scripts/control.py map check
```

It fails (`map_invalid`) on a malformed file and on any quoted control.py line that the
real parser rejects (`dead_commands`).
