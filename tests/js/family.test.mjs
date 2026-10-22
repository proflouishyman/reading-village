// family.js: strict validation of config/family.json (unknown key, wrong type or missing key throws naming the field).
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { validateFamily, setFamily, fam, childPoss, grownUpPoss } from "../../app/js/family.js";

const good = () => ({ v: 1, child: { name: "Sam" }, village_name: "Sam's Village", home_grown_up: "Dad", away_label: "Mom's house" });

test("the committed config/family.json is valid", () => {
  const obj = JSON.parse(readFileSync(new URL("../../config/family.json", import.meta.url)));
  assert.doesNotThrow(() => validateFamily(obj, "config/family.json"));
});

test("a valid family passes and gives possessives", () => {
  setFamily(good());
  assert.equal(fam().child.name, "Sam");
  assert.equal(childPoss(), "Sam's");
  setFamily({ ...good(), home_grown_up: "Mums" });
  assert.equal(grownUpPoss(), "Mums'");
});

test("bad shapes throw naming the field", () => {
  assert.throws(() => validateFamily(null), /must be a JSON object/);
  assert.throws(() => validateFamily({ ...good(), extra: 1 }), /unknown key "extra"/);
  assert.throws(() => validateFamily({ ...good(), v: 2 }), /"v" must be 1/);
  for (const k of ["child", "village_name", "home_grown_up", "away_label"]) {
    const o = good(); delete o[k];
    assert.throws(() => validateFamily(o), new RegExp(`missing required key "${k}"`));
  }
  assert.throws(() => validateFamily({ ...good(), child: {} }), /missing required key "child.name"/);
  assert.throws(() => validateFamily({ ...good(), child: { name: "" } }), /"child.name" must be a non-empty string/);
  assert.throws(() => validateFamily({ ...good(), child: { name: "S", age: 6 } }), /unknown key "child.age"/);
  assert.throws(() => validateFamily({ ...good(), village_name: 5 }), /"village_name" must be a non-empty string/);
  assert.throws(() => validateFamily({ ...good(), away_label: "  " }), /"away_label" must be a non-empty string/);
});
