# Testing habits

- Write the failing test before the fix, when the bug is reproducible in
  under a few minutes. Don't force it for flaky or environment-dependent
  bugs — a regression test after the fact is fine there.
- Prefer one clear assertion per test over a single test that checks five
  things; failures should point at the problem, not require a debugger.
- Don't delete or weaken an existing test to make a change pass. If a test
  is actually wrong, say so and propose the fix separately.
- Run the full suite before calling a change done, not just the tests that
  touch the changed files.
