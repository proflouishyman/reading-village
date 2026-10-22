import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { makeSounds, MASTER_GAIN, applySoundSetting, soundIsOn } from "../../app/js/sounds.js";
import { setFamily } from "../../app/js/family.js";

setFamily({ v: 1, child: { name: "Sam" }, village_name: "Sam's Village", home_grown_up: "Dad", away_label: "Mom's house" });

/** A fake AudioContext that records every oscillator scheduled, so we can check the sounds' shape. */
function fakeAudio() {
  const log = { oscillators: [], ctxs: 0, masterGain: null, destination: {} };
  class Ctx {
    constructor() { log.ctxs++; this.currentTime = 0; this.state = "running"; this.destination = log.destination; }
    createGain() {
      const g = { gain: { value: 1, setValueAtTime() {}, exponentialRampToValueAtTime() {} }, connect(n) { if (n === log.destination) log.masterGain = g; } };
      return g;
    }
    createOscillator() {
      const o = { type: null, frequency: { setValueAtTime() {}, exponentialRampToValueAtTime() {} }, connect() {}, start(t) { o.t0 = t; }, stop(t) { o.t1 = t; } };
      log.oscillators.push(o);
      return o;
    }
  }
  return { Ctx, log };
}
const make = () => {
  const a = fakeAudio();
  const reports = [];
  return { ...a, reports, s: makeSounds({ getAudioContextCtor: () => a.Ctx, report: (m) => reports.push(m) }) };
};

test("every success sound plays gently: master gain 0.25, sine/triangle only", () => {
  const { s, log } = make();
  for (const f of ["pop", "jingle", "fanfare", "thunk", "sparkle"]) assert.ok(s[f]() > 0, f);
  assert.equal(log.masterGain.gain.value, MASTER_GAIN);
  assert.equal(MASTER_GAIN, 0.25);
  assert.ok(log.oscillators.length > 10);
  for (const o of log.oscillators) assert.ok(["sine", "triangle"].includes(o.type), `wave ${o.type}`);
});

test("shapes: jingle has 3 rising notes, fanfare is about 1.5 s, pop and thunk are short", () => {
  let m = make();
  m.s.jingle();
  assert.equal(m.log.oscillators.length, 3);
  assert.ok(m.log.oscillators[0].t0 < m.log.oscillators[1].t0 && m.log.oscillators[1].t0 < m.log.oscillators[2].t0);
  m = make();
  assert.ok(Math.abs(m.s.fanfare() - 1.5) < 0.1);
  assert.ok(make().s.pop() < 0.3);
  assert.ok(make().s.thunk() < 0.3);
});

test("muted: nothing is scheduled and no audio context is even created", () => {
  const { s, log } = make();
  s.setEnabled(false);
  for (const f of ["pop", "jingle", "fanfare", "thunk", "sparkle"]) assert.equal(s[f](), 0);
  assert.equal(log.ctxs, 0);
  assert.equal(log.oscillators.length, 0);
});

test("no miss / try-again sound exists: the player exposes only the five success sounds", () => {
  const { s } = make();
  const fns = Object.keys(s).filter((k) => typeof s[k] === "function" && !["setEnabled", "isEnabled"].includes(k));
  assert.deepEqual(fns.sort(), ["fanfare", "jingle", "pop", "sparkle", "thunk"]);
});

test("an AudioContext that cannot start reports to Dad exactly once and never throws", () => {
  const reports = [];
  const s = makeSounds({ getAudioContextCtor: () => class { constructor() { throw new Error("blocked"); } }, report: (m) => reports.push(m) });
  assert.doesNotThrow(() => { s.pop(); s.jingle(); s.fanfare(); });
  assert.equal(reports.length, 1);
  assert.match(reports[0], /blocked/);
  assert.equal(s.stats.failures, 3); // counted every time, shown once
  const none = makeSounds({ getAudioContextCtor: () => undefined, report: (m) => reports.push(m) });
  assert.doesNotThrow(() => none.pop());
  assert.equal(reports.length, 2);
});

test("settings.sound: missing reads as on, off mutes, anything else is an error", () => {
  applySoundSetting(undefined);
  assert.equal(soundIsOn(), true);
  applySoundSetting("off");
  assert.equal(soundIsOn(), false);
  applySoundSetting("on");
  assert.equal(soundIsOn(), true);
  assert.throws(() => applySoundSetting("loud"));
  assert.throws(() => applySoundSetting(true));
});

test("sounds.js synthesizes everything: it fetches no audio files", () => {
  const src = readFileSync(new URL("../../app/js/sounds.js", import.meta.url), "utf8");
  assert.ok(!/\.(mp3|wav|ogg|m4a)|new Audio\(|fetch\(/.test(src));
});

test("F1: Arial is the default font and settings.font defaults to system", () => {
  const css = readFileSync(new URL("../../app/css/style.css", import.meta.url), "utf8");
  assert.match(css, /:root \{[^}]*--font: Arial,/);
  for (const page of ["index.html", "dashboard.html"]) {
    assert.match(readFileSync(new URL(`../../app/${page}`, import.meta.url), "utf8"), /data-font="system"/);
  }
});
