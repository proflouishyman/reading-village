// Celebration sounds, synthesized with the Web Audio API (no audio files, works offline).
// Rules (docs/design.md): successes only, so there is NO miss / "try again" sound and NO background music.
// Gentle by design: master gain 0.25, sine/triangle waves only (no harsh square or sawtooth).
// If the browser cannot start audio, Dad gets one note (via the injected reporter); the child never sees an error.

export const MASTER_GAIN = 0.25;
export const SOUND_SETTINGS = ["on", "off"];

import { grownUp } from "./family.js";

/**
 * Build a sound player. `AudioContextCtor` is injected so tests can use a fake; `report(message)` is called at
 * most once, the first time audio fails to start or play.
 */
export function makeSounds({ getAudioContextCtor, report }) {
  let enabled = true;
  let ctx = null;
  let master = null;
  let reported = false;
  const stats = { played: 0, failures: 0 };

  function fail(e) {
    stats.failures += 1;
    if (reported) return;
    reported = true;
    report(`Sound could not start (${e && e.message ? e.message : e}). The game works without it; ${grownUp()} can mute it here.`);
  }

  /** Create the context on first use (browsers only allow it after a click, which always precedes a sound). */
  function audio() {
    if (ctx) return ctx;
    const Ctor = getAudioContextCtor();
    if (!Ctor) throw new Error("this browser has no Web Audio");
    ctx = new Ctor();
    master = ctx.createGain();
    master.gain.value = MASTER_GAIN;
    master.connect(ctx.destination);
    return ctx;
  }

  /** One soft note: attack 10ms, exponential decay to silence by start+dur. Returns its end time. */
  function note(c, { freq, endFreq = freq, start = 0, dur = 0.15, type = "triangle", vol = 0.6 }) {
    const t0 = c.currentTime + start;
    const osc = c.createOscillator();
    const env = c.createGain();
    osc.type = type;
    osc.frequency.setValueAtTime(freq, t0);
    if (endFreq !== freq) osc.frequency.exponentialRampToValueAtTime(endFreq, t0 + dur);
    env.gain.setValueAtTime(0.0001, t0);
    env.gain.exponentialRampToValueAtTime(vol, t0 + 0.01);
    env.gain.exponentialRampToValueAtTime(0.0001, t0 + dur);
    osc.connect(env);
    env.connect(master);
    osc.start(t0);
    osc.stop(t0 + dur + 0.02);
    return start + dur;
  }

  /** Run a sound's score if sound is on. Returns its length in seconds (0 when muted or failed). */
  function play(score) {
    if (!enabled) return 0;
    try {
      const c = audio();
      if (c.state === "suspended") Promise.resolve(c.resume()).catch(fail);
      const len = score(c);
      stats.played += 1;
      return len;
    } catch (e) {
      fail(e);
      return 0;
    }
  }

  const C5 = 523.25, E5 = 659.25, G5 = 783.99, C6 = 1046.5;
  return {
    stats,
    /** Turn sound on/off. */
    setEnabled(on) { enabled = on; },
    isEnabled: () => enabled,
    /** Ore from a correct card: a short bubbly pop. */
    pop: () => play((c) => note(c, { freq: 330, endFreq: 700, dur: 0.12, type: "sine", vol: 0.7 })),
    /** Correct word: a rising three-note jingle. */
    jingle: () => play((c) => {
      note(c, { freq: C5, start: 0, dur: 0.13 });
      note(c, { freq: E5, start: 0.13, dur: 0.13 });
      return note(c, { freq: G5, start: 0.26, dur: 0.3 });
    }),
    /** Finished story: a warm fanfare, about 1.5 s. */
    fanfare: () => play((c) => {
      const run = [[392, 0], [C5, 0.18], [E5, 0.36], [G5, 0.54]];
      for (const [f, s] of run) note(c, { freq: f, start: s, dur: 0.2 });
      let end = 0;
      for (const f of [C5, E5, G5]) end = Math.max(end, note(c, { freq: f, start: 0.78, dur: 0.72, vol: 0.45 }));
      note(c, { freq: C6, start: 0.78, dur: 0.72, type: "sine", vol: 0.25 });
      return end;
    }),
    /** Block placed in Build: a soft low thunk. */
    thunk: () => play((c) => note(c, { freq: 150, endFreq: 55, dur: 0.18, type: "sine", vol: 0.9 })),
    /** Emerald: a quick high sparkle. `delay` seconds lets it follow a fanfare. */
    sparkle: (delay = 0) => play((c) => {
      let end = 0;
      [1568, 2093, 2637, 3136, 2637].forEach((f, i) => {
        end = note(c, { freq: f, start: delay + i * 0.07, dur: 0.14, type: "sine", vol: 0.28 });
      });
      return end;
    }),
  };
}

// The app-wide instance. main.js / dashboard.js point `report` at the Dad bar via setSoundReporter.
let reporter = (message) => console.error(message); // replaced at boot by the Dad-bar note
const sounds = makeSounds({
  getAudioContextCtor: () => globalThis.AudioContext ?? globalThis.webkitAudioContext,
  report: (m) => reporter(m),
});

export const setSoundReporter = (fn) => { reporter = fn; };
export const { pop: playPop, jingle: playJingle, fanfare: playFanfare, thunk: playThunk, sparkle: playSparkle } = sounds;

/** Apply settings.sound; a missing value reads as "on" (documented default), anything else is an error. */
export function applySoundSetting(value) {
  const v = value ?? "on";
  if (!SOUND_SETTINGS.includes(v)) throw new Error(`settings.sound must be "on" or "off", got ${JSON.stringify(value)}`);
  sounds.setEnabled(v === "on");
}
export const soundIsOn = () => sounds.isEnabled();
