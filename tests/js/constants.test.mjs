import test from "node:test";
import assert from "node:assert/strict";
import { SMALLCAPS_ADVENTURE, LOWERCASE_TRACK, lowercaseOn } from "../../app/js/constants.js";

const names = (list) => list.map((a) => `${a.stage}${a.track ? ":" + a.track : ""}`);

test("small-caps adventure: blocks, small-caps story, build; no lowercase", () => {
  assert.deepEqual(names(SMALLCAPS_ADVENTURE), ["blocks", "story:smallcaps", "build"]);
});

test("lowercase track: swap-in story, match, mine, build", () => {
  assert.deepEqual(names(LOWERCASE_TRACK), ["story:swap", "match", "mine", "build"]);
});

test("lowercaseOn: missing reads as off", () => {
  assert.equal(lowercaseOn({ settings: { font: "system" } }), false);
  assert.equal(lowercaseOn({ settings: { font: "system", lowercase_track: "off" } }), false);
  assert.equal(lowercaseOn({ settings: { font: "system", lowercase_track: "on" } }), true);
});
