import assert from "node:assert/strict";
import { test } from "node:test";

import { passwordStrength } from "../src/lib/password.ts";

test("empty and short passwords", () => {
  assert.equal(passwordStrength(""), 0);
  assert.equal(passwordStrength("Ab1!"), 1);
  assert.equal(passwordStrength("aaaaaaaaaaaa"), 1);
});

test("strength grows with length and variety", () => {
  assert.equal(passwordStrength("tomatesmarche"), 1);
  assert.equal(passwordStrength("tomates-marche"), 2);
  assert.equal(passwordStrength("Tomates-marche7"), 4);
  assert.equal(passwordStrength("Tomates#Mfou2026"), 4);
  assert.ok(passwordStrength("Tomates2marche") >= 3);
});

test("common sequences lower the score", () => {
  assert.ok(passwordStrength("Password1234!") < passwordStrength("Plantain-Mfou!7"));
  assert.equal(passwordStrength("azertyuiop12"), 1);
});
