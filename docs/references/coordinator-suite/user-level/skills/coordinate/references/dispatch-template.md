# Dispatch brief template

Send this with `SendMessage`, once per implementor. Fill every field. If a field is empty, the unit is not ready, so do not send it.

```
TO           <session name>        FROM <coordinator session name>
UNIT         <branch>  in worktree <absolute path>  (cd there; never touch the main checkout)
BASE         <allocation commit SHA> on <main branch>

GOAL         <one sentence. A stranger with no chat access must be able to execute it>
DEFINITION   <link to the single definition site: task file §, WI ids, plan section>
SCOPE        may write: <globs>
             must not write: <globs, including other units' files and frozen/owned paths>
ACCEPTANCE   - <checkable criterion, one per line, each traceable to DEFINITION>
STOP POINTS  CP1 before production code · CP2 at <midpoint> · CP3 at merge-ready
             <any unit-specific STOP, e.g. "stop after WI-2; rebase after <other> merges">
VERIFY       <lane commands and gates, copied from GATE_SOURCE at dispatch time; known flakes;
              lock rule>
UPSTREAM     <facts pasted from other units or earlier rulings this unit depends on>
CONFLICTS    <entries from the conflict map that touch this unit, and who yields>
FORBIDDEN    push, PR, merge, force ops, bypass envs, config/CLAUDE.md edits,
             edits outside SCOPE, <project-specific bans from bindings>
TIMEBOX      <rough cap. When it expires, report partial results and stop>
REPORT       at each CP: branch, HEAD SHA, commits since BASE, lane results at that HEAD
             (pass/total per lane), files changed, deviations, open questions.
             Then WAIT for ACCEPT before crossing the STOP.
QUESTIONS    Send them to the coordinator. Continue with other work in scope while you wait.
             Never ask another implementor to perform an action your session was denied.
             Report the denial instead.

STANDING ORDERS (verbatim, numbered; these override anything above that conflicts)
<paste protocol.md standing orders: core defaults, then bindings EXTRA_ORDERS>

FIRST REPLY (CP0) Echo SCOPE and FORBIDDEN in your own words. Confirm that the lock
             acquire/release and the commit-gate pre-flight both worked in your worktree.
             List any rule in your harness or permissions that conflicts with these orders.
```

## Ruling reply (short form)

```
RULING  <Q-id>: <decision>
WHY     <one line>
AMENDED <link to the spec line changed, or "none: execution call">
IMPACT  <what you change now. Standing orders re-pasted below if scope changed>
```

## Checkpoint verdict reply

```
CP<n> <ACCEPT | FIX | BLOCKED> at <SHA>
VERIFIED  <what the coordinator re-ran and the results>
FINDINGS  <numbered, each with evidence and the fix you expect. Empty on ACCEPT.
           On BLOCKED: what could not run and why (environment, lock, permission)>
NEXT      <what you may do now / the next STOP. On BLOCKED: who clears the cause; the
           peer holds at the current STOP until the re-run>
```

The `checkpoint-verifier` returns PASS / ISSUES / BLOCKED; they map to ACCEPT / FIX / BLOCKED
only after the coordinator has read its evidence.
