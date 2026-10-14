# Proving a test

Adapted from the team's `/prove-the-test` skill. A green test proves nothing on its own:
it pins a behaviour only if it fails when that behaviour breaks.

> Name the single change to production code that makes this test fail. Then make it, and
> watch it fail. If you cannot name one, the test does not pin what its name claims.

1. Write the test and run it. Watch it fail for the right reason, and keep the failure
   output: the assertion and the values, not "it failed".
2. Implement the fix and watch it pass.
3. Break the production code back in the single smallest way that should defeat this
   test: drop the argument, flip the comparison, remove the guard, restore the old order.
4. Confirm that this test fails. If it stays green, fix the test, not the code.
5. Restore the production code and confirm green again.
6. Report what you broke, which test failed, and its message.

**Revert the sabotage with the inverse edit, never `git checkout -- <file>`**: that
reverts to HEAD and discards the uncommitted fix in the same file.

**The usual way a test fails to discriminate** is a fixture too thin to tell two things
apart:

- a filter test whose fixture has one matching row, so the unfiltered answer is the same;
- a fixture where every record with A also has B, so a filter on the wrong property passes;
- an assertion on a count, where the right number of wrong answers passes;
- a subject that is both "the most recent" and "the one asked for" by construction.

A test that cannot be made to fail is either covered by something else (name it and drop
the test) or a tautology of its own setup (delete it).
