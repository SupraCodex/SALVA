// Shapes of the SALVA API (/api/v1). Kept in sync with backend/app/schemas.

export type Lang = "fr" | "en";
export type RiskLevel = "low" | "medium" | "high";
export type Maturity = "green" | "breaker" | "ripe";
export type Packaging = "crate" | "carton" | "sack";
export type Action = "continue" | "store" | "reroute" | "sell_local" | "optimized_split";
export type RiskProfile = "prudent" | "balanced" | "ambitious";
export type Confidence = "high" | "medium" | "low" | "none";

export interface Quantiles {
  p10: number | null;
  p50: number | null;
  p90: number | null;
}

export interface Sourced {
  value: number | null;
  source: string;
}

export interface Me {
  id: string;
  email: string;
  role: "admin" | "operator";
  locale: Lang;
  organization_id: string;
  organization_name: string;
}

export interface TokenOut {
  access_token: string;
  expires_in: number;
  user: Me;
}

export interface Location {
  id: string;
  code: string;
  label: string;
  kind: string;
  lat: number;
  lon: number;
  source_note: string;
}

export interface Market {
  id: string;
  code: string;
  name: string;
  city: string;
  location_id: string;
  ref_price_fcfa_kg: number;
  absorption_kg_day: number;
  assumption_note: string;
  org_price_fcfa_kg: number | null;
  org_absorption_kg_day: number | null;
}

export interface Product {
  code: string;
  label_fr: string;
  label_en: string;
  source_note: string;
}

/** Price and absorption actually used for an organization: its own value, else the reference. */
export function marketPrice(m: Market): number {
  return m.org_price_fcfa_kg ?? m.ref_price_fcfa_kg;
}

export function marketAbsorption(m: Market): number {
  return m.org_absorption_kg_day ?? m.absorption_kg_day;
}

export interface StorageSite {
  id: string;
  name: string;
  location_id: string;
  location_label: string;
  capacity_kg: number;
  temp_mode: "ambient_shade" | "ventilated" | "cold_room";
  cost_fcfa_kg_day: number;
  is_active: boolean;
}

export interface LatestAnalysis {
  id: string;
  analysis_at: string;
  risk_level: RiskLevel;
  loss_p50: number;
  simulation_id: string | null;
  recommended_action: Action | null;
  confidence: Confidence | null;
  no_clear_winner: boolean | null;
}

export interface Lot {
  id: string;
  product_code: string;
  quantity_kg: number;
  harvested_at: string;
  maturity: Maturity;
  packaging: Packaging;
  origin_location_id: string;
  origin_label: string;
  destination_market_id: string;
  destination_name: string;
  destination_city: string;
  eta_planned_at: string;
  eta_current_at: string;
  delay_h: number;
  temp_override_c: number | null;
  price_override_fcfa_kg: number | null;
  notes: string | null;
  status: "open" | "decided" | "closed";
  created_at: string;
  latest_analysis: LatestAnalysis | null;
}

export interface LotList {
  items: Lot[];
  next_cursor: string | null;
}

export interface Enrichment {
  temperature: Sourced;
  temperature_available: boolean;
  diurnal_amp_c: Sourced;
  route_km: Sourced;
  route_hours: Sourced;
  price_fcfa_kg: Sourced;
  suggested_eta_at: string | null;
}

export interface Factor {
  name: string;
  contribution: number;
  direction: "increases_risk" | "decreases_risk" | "neutral";
}

export interface Analysis {
  id: string;
  lot_id: string;
  analysis_at: string;
  replay: boolean;
  model: { name: string; version: string; fallback: boolean };
  inputs: {
    age_h: number;
    remaining_transit_h: number;
    delay_h: number;
    total_delay_h: number;
    temp_mean_c: Sourced;
    diurnal_amp_c: Sourced;
    product_temp_mean_c: number;
    degree_hours_above_ref: number;
    price_fcfa_kg: Sourced;
    quantity_kg: number;
    maturity: Maturity;
    packaging: Packaging;
  };
  risk: {
    level: RiskLevel;
    loss_fraction: Quantiles;
    interval_width: number;
    loss_reason: string;
    uncertainty_reason: string;
  };
  top_factors: Factor[];
  shelf_life_p50_h: number | null;
  extrapolated_features: string[];
  disclaimer_code: string;
  created_at: string;
}

export interface Assumption {
  key: string;
  value: number | string | null;
  unit: string;
  source: string;
  user_override: boolean;
}

export interface AllocationLine {
  scenario_key: string;
  action: Action;
  label: Record<Lang, string>;
  kg: number;
  full_price_kg: number;
  surplus_kg: number;
}

export interface Scenario {
  id: string;
  key: string;
  action: Action;
  label: Record<Lang, string>;
  market_id: string | null;
  storage_site_id: string | null;
  feasible: boolean;
  infeasible_reason: string | null;
  discouraged: boolean;
  discouraged_reason: string | null;
  loss: Quantiles;
  recoverable_kg: Quantiles;
  gross_value_fcfa: Quantiles;
  net_value_fcfa: Quantiles;
  prob_best: number;
  risk_level: RiskLevel | null;
  allocation: AllocationLine[];
  discarded_kg: number;
  storage_used_kg: number;
  extra_h: number;
  hold_h: number;
  transit_saving_h: number;
  cost_p50_fcfa: number;
  extrapolation_warnings: string[];
}

export interface Recommendation {
  id: string;
  simulation_id: string;
  best_scenario_id: string | null;
  best_scenario_key: string | null;
  best_action: Action | null;
  confidence: Confidence;
  no_clear_winner: boolean;
  prob_best: number;
  gap_fraction: number | null;
  rationale_codes: string[];
  ranked_scenario_ids: string[];
  candidate_scenario_ids: string[];
  low_risk: boolean;
  policy: { risk_profile: RiskProfile; lam: number; materiality: number };
  assumption_codes: string[];
}

export interface Simulation {
  id: string;
  analysis_id: string;
  lot_id: string;
  n_draws: number;
  seed: number;
  risk_profile: RiskProfile;
  duration_ms: number;
  assumptions: Assumption[];
  scenarios: Scenario[];
  recommendation: Recommendation;
  created_at: string;
}

export interface MarketOverride {
  price_fcfa_kg?: number;
  absorption_kg?: number;
}

export interface SimulationRequest {
  n_draws?: number;
  seed?: number;
  risk_profile: RiskProfile;
  assumptions: {
    markets: Record<string, MarketOverride>;
    hold_h?: number;
    transport_fcfa_kg_km?: number;
    surplus_price_fraction?: number;
  };
}

export interface Explanation {
  id: string;
  recommendation_id: string;
  lang: Lang;
  source: "llm" | "template";
  provider: string | null;
  validated: boolean;
  summary: string;
  risk_explanation: string;
  scenario_comparison: string;
  recommendation_text: string;
  caveats: string[];
  created_at: string;
}

export interface SensitivityPoint {
  temp_c: number;
  delay_h: number;
  best_scenario_key: string | null;
  best_action: Action | null;
  confidence: Confidence;
}

export interface Sensitivity {
  simulation_id: string;
  n_draws: number;
  seed: number;
  current: { temp_c: number; delay_h: number };
  temperatures_c: number[];
  delays_h: number[];
  points: SensitivityPoint[];
  transitions: {
    axis: "temperature" | "delay";
    from_value: number;
    to_value: number;
    fixed_value: number;
    from_action: Action | null;
    to_action: Action | null;
  }[];
}

export interface Outcome {
  id: string;
  lot_id: string;
  simulation_run_id: string | null;
  scenario_id: string | null;
  decision_taken: Action | "other";
  followed_reco: boolean | null;
  actual_recovered_kg: number | null;
  actual_revenue_fcfa: number | null;
  recorded_at: string;
}

export interface LotHistory {
  lot_id: string;
  analyses: {
    id: string;
    analysis_at: string;
    replay: boolean;
    risk_level: RiskLevel;
    loss_p10: number;
    loss_p50: number;
    loss_p90: number;
    model_version: string;
    simulations: {
      id: string;
      created_at: string;
      risk_profile: RiskProfile;
      n_draws: number;
      seed: number;
      best_action: Action | null;
      best_scenario_key: string | null;
      confidence: Confidence;
      no_clear_winner: boolean;
      user_overrides: number;
    }[];
  }[];
  outcomes: Outcome[];
}

export interface Parameter {
  name: string;
  value: unknown;
  unit: string;
  description: string;
  source: string;
  reference: string | null;
  note: string | null;
}

export interface Assumptions {
  product: string;
  product_file_sha256: string;
  parameters: Parameter[];
  economics: { name: string; value: number; unit: string; source: string }[];
  markets: Market[];
  model: { production: string; version: string; fallback: boolean; experimental: string | null; verdict: string | null };
  limits: string[];
}

export interface UserRow {
  id: string;
  email: string;
  role: "admin" | "operator";
  locale: Lang;
  is_active: boolean;
  created_at: string;
}

export interface Health {
  status: string;
  database: string;
  llm_provider: string;
  weather_enabled: boolean;
  model: { name: string; version: string; fallback: boolean } | null;
}

export interface QuestionAnswer {
  kind: "what_if" | "risk" | "recommendation" | "why" | "uncertainty" | "assumptions" | "unsupported";
  answer: string;
  what_if: {
    changes: Record<string, number | string>;
    best_label: { fr: string; en: string } | null;
    best_action: Action | null;
    confidence: Confidence;
    no_clear_winner: boolean;
    net_value_fcfa: Quantiles;
    loss_fraction: Quantiles;
    current_best_label: { fr: string; en: string } | null;
    current_net_p50_fcfa: number | null;
  } | null;
}
