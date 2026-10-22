// Generic Dad-judged loop shared by Letter Mine and Word Blocks.
import { victoryItem } from "../rules.js";
import { cueBox, popReward } from "../ui.js";

const REQUEUE_GAP = 3; // a missed item comes back this many cards later

/**
 * Run entries through Dad's judgement.
 *  entries: array of items to show (any objects)
 *  show(entry): renders the card into L.play and returns the element ore pops should anchor to
 *  cueFor(entry): array of cue objects (from cues.json) to show on "Let's try again" (may be empty)
 *  againHint: optional text for Dad's bar while a "try again" is in progress (used when there is no cue)
 *  record(entry, result): async; saves the result and returns the reward kind (or null)
 * Flow per entry: Got it -> correct. Let's try again -> show cue -> Got it = assisted;
 * try again a second time = miss (recorded, card requeued once, comes back later).
 * The stage always ends on a clean success: a victory card, taken from the items he got right on his own
 * and offering Dad only "Got it!", so it can never record a miss. Only if he got nothing right independently
 * is the first entry used, and then Got it is recorded as "assisted" (he has been helped through it).
 * Returns "done" or "quit".
 */
export async function runJudged(L, { entries, show, cueFor, record, againHint }) {
  const queue = entries.slice();
  const requeued = new Set();
  const history = [];

  const normalHint = L.hint.textContent;
  let done = 0; // cards finished so far (any result); drives the child's progress row

  // Row length = finished + this card + still queued (+ the victory card). Re-queued cards extend it. The victory
  // card is counted up front as the last pip; if the final card turns out to be a clean success there is none and
  // the row simply ends one pip shorter (finish() below).
  const showProgress = (extra) => L.setProgress(done, done + 1 + queue.length + extra);

  async function judgeOne(entry, { allowRequeue, victory = false, victoryResult = "correct" }) {
    L.cue.replaceChildren();
    const anchor = show(entry);
    showProgress(victory ? 0 : 1);
    let result;
    if (victory) {
      if ((await L.choose("", { allowAgain: false })) === "quit") return "quit";
      result = victoryResult;
    } else {
      let choice = await L.choose();
      if (choice === "quit") return "quit";
      if (choice === "again") {
        L.cue.replaceChildren(...cueFor(entry).map(cueBox));
        if (againHint) L.setHint(againHint);
        choice = await L.choose("Come back to it later");
        L.setHint(normalHint);
        if (choice === "quit") return "quit";
        result = choice === "got" ? "assisted" : "miss";
      } else {
        result = "correct";
      }
    }
    const reward = await record(entry, result);
    history.push({ item: entry, result });
    done += 1;
    if (reward) popReward(anchor, reward);
    if (result === "miss" && allowRequeue && !requeued.has(entry)) {
      requeued.add(entry);
      queue.splice(Math.min(REQUEUE_GAP, queue.length), 0, entry);
    }
    await new Promise((r) => setTimeout(r, result === "miss" ? 250 : 1100));
    return "ok";
  }

  while (queue.length) {
    const r = await judgeOne(queue.shift(), { allowRequeue: true });
    if (r === "quit") return "quit";
  }
  const again = victoryItem(history, entries[0]);
  if (again === null) L.setProgress(done, done); // no victory card: every pip filled
  if (again !== null) {
    const independent = history.some((x) => x.result === "correct");
    const r = await judgeOne(again, { allowRequeue: false, victory: true, victoryResult: independent ? "correct" : "assisted" });
    if (r === "quit") return "quit";
    L.setProgress(done, done);
  }
  return "done";
}
