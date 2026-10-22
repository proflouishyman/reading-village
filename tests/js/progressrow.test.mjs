import test from "node:test";
import assert from "node:assert/strict";
import { runJudged } from "../../app/js/screens/judged.js";

/** A fake stage layout: Dad's answers come from a script; every setProgress call is recorded. */
function fakeLayout(answers) {
  const calls = [];
  const L = {
    hint: { textContent: "" }, cue: { replaceChildren() {} },
    setHint() {}, setProgress: (d, t) => calls.push([d, t]),
    choose: async () => answers.shift(),
  };
  return { L, calls };
}
const run = (answers, entries) => {
  const { L, calls } = fakeLayout(answers);
  return runJudged(L, { entries, show: () => ({ append() {} }), cueFor: () => [], record: async () => null }).then((r) => ({ r, calls }));
};

test("the row advances one card at a time and ends full", async () => {
  // a, b both "correct"; the last card was a clean success so there is no victory card.
  const { r, calls } = await run(["got", "got"], [{ id: "a" }, { id: "b" }]);
  assert.equal(r, "done");
  assert.deepEqual(calls[0], [0, 3]); // victory pip counted up front
  assert.deepEqual(calls[1], [1, 3]);
  assert.deepEqual(calls.at(-1), [2, 2]);
});

test("a miss extends the row and is filled like any other card", async () => {
  // a: try again twice (miss, re-queued); b correct; a again correct; then victory is not needed (last was correct).
  const { calls } = await run(["again", "again", "got", "got"], [{ id: "a" }, { id: "b" }]);
  const totals = calls.map(([, t]) => t);
  assert.ok(Math.max(...totals) >= 4, `row should have grown, got ${JSON.stringify(calls)}`);
  assert.deepEqual(calls.at(-1), calls.at(-1).map(() => calls.at(-1)[0]), "ends with every pip filled");
  for (const [d, t] of calls) assert.ok(d <= t);
});

test("the victory card is the last pip", async () => {
  // single card assisted -> victory card is shown; row total includes it.
  const { calls } = await run(["again", "got", "got"], [{ id: "a" }]);
  assert.deepEqual(calls[0], [0, 2]);
  assert.deepEqual(calls.find((c) => c[0] === 1), [1, 2]);
  assert.deepEqual(calls.at(-1), [2, 2]);
});
