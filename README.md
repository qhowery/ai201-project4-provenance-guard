# Provenance Guard — AI201 Project 4

**Student:** Quonlee Howery · qhowery@princeton.edu

Backend system that classifies submitted text, scores AI-vs-human likelihood, surfaces transparency labels, and logs decisions for appeals.

## Setup

```bash
cd ai201-project4-provenance-guard
pip install -r requirements.txt
cp .env.example .env   # add GROQ_API_KEY
python app.py
```

Server runs at `http://localhost:5000`.

## Milestone 3 — Test

```bash
curl -s -X POST http://localhost:5000/submit \
  -H "Content-Type: application/json" \
  -d '{"text": "The sun dipped below the horizon, painting the sky in hues of amber and rose. I sat on the porch, coffee in hand, watching the neighborhood slowly go quiet.", "creator_id": "test-user-1"}' | python -m json.tool

curl -s http://localhost:5000/log | python -m json.tool
```

## Project structure

```
app.py                  # Flask routes: POST /submit, GET /log
config.py               # Settings and paths
audit.py                # JSONL audit log + in-memory submission store
signals/
  llm_classifier.py     # Signal 1 — Groq LLM classifier (Milestone 3)
planning.md             # Full spec (Milestones 1–2)
logs/audit.jsonl        # Written at runtime (gitignored)
```

## Status

- [x] Milestone 1 — Architecture
- [x] Milestone 2 — Spec
- [x] Milestone 3 — `POST /submit` + Signal 1 + audit log + `GET /log`
- [ ] Milestone 4 — Signal 2 + confidence fusion
- [ ] Milestone 5 — Labels + appeals
