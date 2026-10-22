// The save queue: every progress/event save in a page goes through one committer, so PUTs never overlap.
// Pure of the DOM (the banner and sound hooks are injected) so tests can drive it with a fake server.
//
// Optimistic concurrency (docs/design.md): progress carries an integer `rev`. A PUT carries the rev it was
// based on; the server answers 409 if that is stale. On a 409 we GET the fresh progress and apply the SAME
// mutate function to it once more. That is correct, not a fallback: a mutation is a function of state
// ("add one wood", "set font"), so re-applying it to newer state keeps the other tab's changes and ours.
// A second 409 in a row is not retried again: it locks with the NOT SAVED banner.
import { ApiError } from "./api.js";

/** Return false from a mutate function to say "nothing to do": nothing is saved or logged. */
export const SKIP = false;

/**
 * @param api      { getProgress, putProgress, postEvent }
 * @param state    { progress, locked } shared mutable state (the store object)
 * @param makeEvent(fields) -> full event
 * @param onProgress(progress) called whenever state.progress is replaced
 * @param onLock(reason, retry) show the NOT SAVED banner; onUnlock() hide it
 * @param onEvent(reply)  optional: called with the server's reply to every accepted event (it may carry new
 *                        treasure / a level-up); a throw is a bug and propagates loudly
 */
export function createCommitter({ api, state, makeEvent, onProgress, onLock, onUnlock, onEvent }) {
  let unlockWaiters = [];
  let tail = Promise.resolve();

  const setProgress = (p) => {
    if (!Number.isInteger(p.rev) || p.rev < 0) throw new Error(`progress from the server has no integer rev (got ${p.rev})`);
    state.progress = p;
    onProgress(p);
  };

  /** Load progress from the server (throws ApiError; callers show it loudly). */
  async function load() {
    const p = await api.getProgress();
    if (p.v !== 1) throw new Error(`progress.json has unexpected version ${p.v}`);
    setProgress(p);
    return p;
  }

  function lock(reason) {
    state.locked = true;
    onLock(reason, retry);
  }

  /** Banner button: re-read progress from the server; unlock only if that works. */
  async function retry() {
    try {
      await load();
    } catch (e) {
      lock(e.message);
      return;
    }
    state.locked = false;
    onUnlock();
    const waiters = unlockWaiters;
    unlockWaiters = [];
    waiters.forEach((r) => r());
  }

  const whenUnlocked = () => new Promise((r) => unlockWaiters.push(r));

  /** Apply mutate to a copy and PUT it (with `cause`, the event this save belongs to, or null). Returns true when
   *  saved, false when mutate said SKIP. */
  async function saveMutation(mutate, cause) {
    for (let attempt = 0; ; attempt++) {
      const next = structuredClone(state.progress);
      if (mutate(next) === SKIP) return false;
      try {
        setProgress(await api.putProgress(next, cause ?? undefined));
        return true;
      } catch (e) {
        if (!(e instanceof ApiError) || e.status !== 409) throw e;
        if (attempt >= 1) throw new ApiError(`another window changed the progress twice while saving (${e.message})`, 409);
        await load(); // fresh state, then the loop applies the same mutate once more
      }
    }
  }

  async function commit(fields, mutate) {
    let progressDone = !mutate;
    let eventDone = fields === null;
    // Built ONCE: a retry after a failed save must re-post the identical event (same ts), so the server's
    // idempotency key (a hash of the event) matches and it does not grant the treasure twice. The same event
    // rides along with the progress PUT as its `cause`, so the history names what earned/spent the resources.
    const event = fields === null ? null : makeEvent(fields);
    for (;;) {
      while (state.locked) await whenUnlocked();
      try {
        // Progress first: a mutate that turns out to be a no-op (SKIP) must not leave an event behind.
        if (!progressDone) {
          if (!(await saveMutation(mutate, event))) return false;
          progressDone = true;
        }
        if (!eventDone) {
          const reply = await api.postEvent(event);
          eventDone = true;
          if (onEvent) {
            onEvent(reply);
            // The server added to progress.treasure and bumped rev: refresh our copy rather than earn a 409 next save.
            if (reply.treasure?.length) await load();
          }
        }
        return true;
      } catch (e) {
        if (!(e instanceof ApiError)) throw e; // a bug, not a save failure: let it be loud elsewhere
        lock(e.message);
      }
    }
  }

  return {
    load,
    retry,
    /**
     * Log an event (if `fields` given) and apply `mutate` to a copy of progress (if given), saving both.
     * Calls are serialised. Resolves true when saved, false when mutate returned SKIP. On a save failure
     * shows the banner and resumes after Dad resolves it.
     */
    commit(fields, mutate) {
      const run = tail.then(() => commit(fields, mutate));
      // The caller sees run's rejection; the chain itself must keep going for later saves.
      tail = run.catch(() => {});
      return run;
    },
  };
}
