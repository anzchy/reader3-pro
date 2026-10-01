# Checkpoint acceptance checklists

Every verdict gets one row in `ledger.tsv`, keyed to the SHA. A new SHA reopens that checkpoint.
A report is evidence for a verdict, not the verdict itself.

## CP0: Acknowledgement (before any work)
- [ ] The peer restated SCOPE and FORBIDDEN correctly, with no widened globs.
- [ ] Pre-flight passed in the peer's worktree:
  - [ ] each lock works (the wrapper reports `status`, or acquire and release both succeeded)
  - [ ] the commit gate is runnable
  - [ ] the declared gate tool, if any, is ready
- [ ] Harness or permission conflicts are listed. Each one is either resolved with the user or
      recorded as "settle at merge", with the user's agreement.
- Reject if a peer "will just work around" a denied action. Escalate the denial instead.

## CP1: Design (plan plus test matrix, before production code)
- [ ] The work items map 1:1 to ACCEPTANCE. Nothing extra and nothing missing.
- [ ] **Traceability:** every test assertion cites a clause in the definition site. For each
      untraceable assertion, remove it, or report it as a finding the coordinator can promote to
      the spec. When it exposes a real defect, log the defect as debt with an owner. Do not keep
      the assertion.
- [ ] The tests assert behaviour: they call the code the way users do and check literal
      expected values. No wiring-only tests.
- [ ] The matrix includes the failure and boundary cases the spec names. For a risky unit,
      optionally run an adversary pass that searches for a wrong implementation that passes
      every case.
- [ ] Owned or frozen paths are touched only by their owner.
- [ ] Conflict-map entries for this unit are acknowledged in the plan.
- [ ] Spec contradictions found while planning are raised as questions, not silently resolved.

## CP2: Midpoint (commit gate green)
- [ ] Commit-gate lanes are green **at the reported SHA**. Re-run the decisive one yourself or
      through the verifier.
- [ ] `git diff <BASE>..<SHA> --stat` stays within SCOPE.
- [ ] The owned and frozen paths diff is empty for non-owners.
- [ ] Deviations since CP1 are explained, and each was ruled on or logged.
- [ ] No bypass flags or disabled tests, and no weakened assertions: check that no test deleted
      in the diff lacks a ruling.

## CP3: Merge-ready (push gate green plus review)
- [ ] Push-gate lanes are green at the SHA. E2E and other contended lanes ran **under the lock**.
      Re-run the decisive lane yourself at that SHA.
- [ ] Every ACCEPTANCE line is met, with evidence (test name, log line, screenshot).
- [ ] A review ran in a fresh context (the gate tool's review step or the
      `checkpoint-verifier` subagent). Findings were triaged: correctness or requirement gaps are fixed, the rest are
      optional.
- [ ] Rebased onto the current main branch if an earlier merge in the order landed; ledger rows
      from the old base are superseded. Recount and re-run whatever the conflict map says the
      second merge must redo.
- [ ] The final owned and frozen paths diff is clean.
- [ ] Commit messages follow the harness pins, or the conflict is listed for the user.
- [ ] Logged debts have an owner and a location.
- Verdict: ACCEPT hands the branch to the user to merge. The coordinator never merges.
