import assert from "node:assert/strict";
import { test } from "node:test";

import { addHours, fcfa, fromLocalInput, hours, kg, pct, sig } from "../src/lib/format.ts";

// Intl inserts narrow no-break spaces as French group separators; compare digits only.
const digits = (s: string) => s.replace(/[\s  ]/g, "");

test("currency and weights are rounded and labelled", () => {
  assert.equal(digits(fcfa(177635.4, "fr")), "177635FCFA");
  assert.equal(fcfa(177635.4, "en"), "177,635 FCFA");
  assert.equal(kg(299.6, "en"), "300 kg");
  assert.equal(fcfa(null, "en"), "–");
});

test("percentages and hours", () => {
  assert.equal(pct(0.404, "en"), "40%");
  assert.equal(hours(4.25, "en"), "4.3 h");
  assert.equal(hours(18.4, "en"), "18 h");
  assert.equal(pct(Number.NaN, "fr"), "–");
});

test("small model parameters keep significant digits", () => {
  assert.equal(sig(0.003, "en"), "0.003");
  assert.equal(sig(0.0254, "en"), "0.0254");
  assert.equal(sig(2.2, "en"), "2.2");
  assert.equal(sig(0, "en"), "0");
});

test("date helpers round-trip through ISO strings", () => {
  assert.equal(addHours("2026-10-03T08:00:00.000Z", 12), "2026-10-03T20:00:00.000Z");
  assert.equal(fromLocalInput(""), null);
  assert.equal(fromLocalInput("not a date"), null);
  const iso = fromLocalInput("2026-10-03T08:00");
  assert.ok(iso && !Number.isNaN(Date.parse(iso)));
});
