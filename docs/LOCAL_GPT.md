# Run ShockFlow AI locally with your GPT key (and optional Neo4j graph)

Everything runs **offline by default** (deterministic mock provider, in-memory graph). Add an OpenAI
key to switch the **real** paths on — GPT-4o event extraction and the **GraphRAG operator copilot** —
without changing any code. This is the "put the key in → the operator screen runs everything" setup.

---

## 1. Install

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[api,ml,llm]"        # llm extra pulls the openai (and anthropic) SDKs
cd apps/web && npm install && cd ../..
```

## 2. Put your GPT key in `.env`

Copy `.env.example` to `.env` and set:

```env
LLM_PROVIDER=openai
OPENAI_API_KEY=sk-...          # your key
OPENAI_MODEL=gpt-4o            # default; any chat model you have access to
```

That single change turns on **two** real paths — no other flags needed:

| Path | With `LLM_PROVIDER=mock` (default) | With `LLM_PROVIDER=openai` + key |
| --- | --- | --- |
| **Event extraction** (news → events) | deterministic keyword mock | **GPT-4o** structured extraction (grounded, cited) |
| **Operator copilot** (`운영 도우미`) | rule-based, allowlisted intents | **GraphRAG**: GPT-4o answers over the as-of event graph |

Both **degrade safely**: if the key/SDK is missing or a call errors, they fall back to the offline
path — they never fabricate an event or an answer.

## 3. Run the API + web

```bash
make api      # http://127.0.0.1:8000   (FastAPI)
make web      # http://localhost:3000   (Next.js operator + rider screens)
```

Open **http://localhost:3000/statistics** (operator statistics). The **운영 도우미** panel now answers
through GraphRAG:

- Ask e.g. *"미드타운 왜 붐벼?"* or *"지금 무슨 일 있어?"*.
- The answer carries a **⚡ GraphRAG · OPENAI** badge (vs **📐 규칙 기반** when no key).
- Cited events are listed with their ids, **validated against the graph** — the copilot cannot cite
  an event that is not really in the as-of context. Forecast changes are labelled model-attributed,
  not causal.

### How GraphRAG stays grounded

The event graph (`Article → Event → H3Zone → Feature → Forecast`) is the **retrieval substrate**. For
each question the API assembles the as-of events, their grounded evidence, the zones they affect, and
the model-attributed forecast delta, then asks GPT-4o to answer **using only that context and citing
event ids**. Cited ids are filtered to those actually present, so answers stay grounded (CLAUDE.md
§22). See `services/api/graphrag.py`.

## 4. Build the event graph from real data (optional)

```bash
make seed-graph        # news + NYC permitted events → in-memory graph + JSON snapshot
```

Writes `data/processed/graph/event_graph.json` (2,090 events / 5,770 nodes at the default cap).

### Push it to a real Neo4j (optional)

```bash
docker compose up -d neo4j                       # local Neo4j on bolt://localhost:7687
export NEO4J_PASSWORD=shockflow_dev              # match docker-compose.yml
pip install -e ".[graph]"
python -m scripts.build_graph --backend neo4j    # writes the graph to the live server
#   add --permitted-limit -1 to load all ~63k permitted events
```

Browse it at **http://localhost:7474** (Neo4j Browser), e.g.:

```cypher
MATCH (a:Article)-[:REPORTS]->(e:Event)-[:AFFECTS]->(z:H3Zone) RETURN a,e,z LIMIT 50;
```

The graph is an **audit/provenance surface** (§9). Forecasting features stay pure functions and do
not depend on it, so the demo works with or without Neo4j.

## 5. Verify

```bash
make test                                  # offline suite (mock provider)
python -m ml.forecasting.lift_direction    # directional lift (streams trip data; minutes)
```

> **Cost note:** with `LLM_PROVIDER=openai`, extraction and each copilot question call the OpenAI API
> (your key, your usage). Demo Mode (`mock`) is free and offline — use it for tests and the golden path.
