import assert from "node:assert/strict";
import { test } from "node:test";

import { fieldErrors, translate, translateDynamic } from "../src/lib/i18n.tsx";
import { en, fr } from "../src/lib/messages.ts";

const placeholders = (s: string) => [...s.matchAll(/\{(\w+)\}/g)].map((m) => m[1]).sort();

test("French and English dictionaries have the same keys", () => {
  assert.deepEqual(Object.keys(en).sort(), Object.keys(fr).sort());
});

test("translations keep the same placeholders and are never empty", () => {
  for (const key of Object.keys(fr) as (keyof typeof fr)[]) {
    assert.ok(fr[key].trim(), `empty fr ${key}`);
    assert.ok(en[key].trim(), `empty en ${key}`);
    assert.deepEqual(placeholders(en[key]), placeholders(fr[key]), key);
  }
});

test("variables are substituted and unknown dynamic keys fall back", () => {
  assert.equal(translate("en", "common.requestId", { id: "abc" }), "Reference: abc");
  assert.equal(translateDynamic("en", "reason.UNKNOWN_CODE", "raw"), "raw");
});

test("API field errors are mapped to translated messages with limits", () => {
  const td = (key: string, fallback?: string) => translateDynamic("en", key, fallback);
  const out = fieldErrors(
    [
      { field: "quantity_kg", code: "greater_than", message: "Input should be greater than 0" },
      { field: "quantity_kg", code: "missing", message: "second error ignored" },
      { field: null, code: "strange", message: "Server says no" },
    ],
    td,
  );
  assert.equal(out.quantity_kg, "The value must be greater than 0.");
  assert.equal(out._, "Server says no");
});
