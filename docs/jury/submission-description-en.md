# SALVA — submission description (English draft)

## What it does

SALVA helps a trader decide what to do with a perishable produce lot while it is in transit. The user enters a small set of facts about a tomato lot. SALVA estimates a range of commercial value loss, compares feasible actions such as continuing, storing, rerouting, selling locally or splitting the lot, and explains the recommendation.

The numbers come from a deterministic kinetic model and Monte Carlo decision simulations. A language model is optional and can only rewrite computed facts; a checked template is always available. SALVA clearly labels assumptions and states that the model has not been validated on field data.

## Who it is for

The MVP is for a tomato trader or cooperative manager shipping a lot from western Cameroon to an urban market such as Douala or Yaoundé, often without sensors and with variable connectivity.

## What to show

Use the English interface and the 500 kg demonstration lot. Show the risk range, decision simulations, a changed market/storage assumption, the recommendation, a constrained “what if” question, and the assumptions and limits page. The versioned backup recording is [`docs/demo/SALVA_demo_en.mp4`](../demo/SALVA_demo_en.mp4).

## Testing instructions

Requirements: Python 3.11+, Node.js 20+, PostgreSQL 16+, and Git.

```bash
cp .env.example .env
# Set a long JWT_SECRET and DATABASE_URL in .env.
# For an offline demo also set WEATHER_ENABLED=false and LLM_PROVIDER=template.
docker compose up --build
```

Open `http://localhost:8000`. Create an account, use **New lot**, choose **Prefill the example lot**, then create and analyse it. Follow **Risk → Decisions → Recommendation**. The application remains usable with the language model disabled and labels weather/routing fallbacks as assumptions.

For a local test suite:

```bash
make install
make test
make e2e SALVA_URL=http://127.0.0.1:8000
```

The project is a proof of concept. Its production kinetic model is based on literature ranges and assumptions; its ML surrogate is experimental and currently NO-GO. No field accuracy or revenue improvement should be inferred from the displayed estimates.
