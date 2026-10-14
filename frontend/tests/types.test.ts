import assert from "node:assert/strict";
import { test } from "node:test";

import { marketAbsorption, marketPrice, type Market } from "../src/lib/types.ts";

const base: Market = {
  id: "m",
  code: "M01",
  name: "Marché Mboppi",
  city: "Douala",
  location_id: "l",
  ref_price_fcfa_kg: 600,
  absorption_kg_day: 4000,
  assumption_note: "reference",
  org_price_fcfa_kg: null,
  org_absorption_kg_day: null,
};

test("the organization's market values replace the reference ones", () => {
  assert.equal(marketPrice(base), 600);
  assert.equal(marketAbsorption(base), 4000);
  const own = { ...base, org_price_fcfa_kg: 650, org_absorption_kg_day: 0 };
  assert.equal(marketPrice(own), 650);
  assert.equal(marketAbsorption(own), 0);
});
