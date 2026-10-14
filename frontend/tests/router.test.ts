import assert from "node:assert/strict";
import { test } from "node:test";

import { match } from "../src/lib/router.tsx";

test("route patterns extract parameters", () => {
  assert.deepEqual(match("/lots/:id/:tab", "/lots/abc/simulation"), { id: "abc", tab: "simulation" });
  assert.deepEqual(match("/lots/:id", "/lots/a%20b/"), { id: "a b" });
  assert.equal(match("/lots/:id", "/lots/abc/analysis"), null);
  assert.equal(match("/history", "/assumptions"), null);
});
