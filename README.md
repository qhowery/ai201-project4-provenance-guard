# Provenance Guard — AI201 Project 4

**Student:** Quonlee Howery · qhowery@princeton.edu

Backend system that classifies submitted text, scores AI-vs-human likelihood, surfaces transparency labels, handles appeals, and logs every decision.

## Setup

```bash
cd ai201-project4-provenance-guard
pip install -r requirements.txt
cp .env.example .env   # add GROQ_API_KEY
python app.py
```

Server runs at `http://localhost:5000`.

## API endpoints

| Method | Path | Purpose |
|--------|------|---------|
| `POST` | `/submit` | Classify text → transparency label |
| `POST` | `/appeal` | Creator challenges a classification |
| `GET` | `/log` | Audit trail (submissions + appeals) |

## Test commands

### Submit
```bash
curl -s -X POST http://localhost:5000/submit \
  -H "Content-Type: application/json" \
  -d '{"text": "The sun dipped below the horizon, painting the sky in hues of amber and rose. I sat on the porch, coffee in hand, watching the neighborhood slowly go quiet.", "creator_id": "test-user-1"}' | python -m json.tool
```

### Appeal (use `content_id` from submit response)
```bash
curl -s -X POST http://localhost:5000/appeal \
  -H "Content-Type: application/json" \
  -d '{"content_id": "PASTE-CONTENT-ID-HERE", "creator_id": "test-user-1", "creator_reasoning": "I wrote this myself from personal experience. I am a non-native English speaker and my writing style may appear more formal than typical."}' | python -m json.tool
```

### Audit log
```bash
curl -s http://localhost:5000/log | python -m json.tool
```

### Automated test suites
```bash
python test_milestone4.py   # dual-signal scoring (4 inputs)
python test_milestone5.py   # labels, appeals, rate limiting
```

## Transparency labels

Three variants — label and attribution change with confidence score:

| Label | Example attribution |
|-------|---------------------|
| `high-confidence AI` | This content was assessed as AI-generated (88% confidence). |
| `high-confidence human` | This content was assessed as human-written (12% confidence). |
| `uncertain` | This content could not be confidently attributed (55% confidence). Attribution is uncertain. |

## Rate limiting

`POST /submit` is limited to **`10 per minute; 100 per day`** per IP address.

**Why these limits:**
- **10/minute** — allows a writer to submit several drafts in a session without enabling scripted flooding
- **100/day** — generous cap for legitimate daily use while blocking sustained abuse

Test (run while server is active):
```bash
for i in $(seq 1 12); do
  curl -s -o /dev/null -w "%{http_code}\n" -X POST http://localhost:5000/submit \
    -H "Content-Type: application/json" \
    -d '{"text": "This is a test submission for rate limit testing purposes only.", "creator_id": "ratelimit-test"}'
done
```

**Expected output** (verified via `test_milestone5.py`):
```
200 200 200 200 200 200 200 200 200 200 429 429
```

## Audit log fields

Each **classification** entry includes:
`timestamp`, `content_id`, `creator_id`, `llm_score`, `stylo_score`, `confidence`, `divergence`, `label`, `attribution`, `status`, `appeal_filed`

Each **appeal** entry includes:
`appeal_reasoning`, `appeal_timestamp`, original scores/label, `status: under_review`

After an appeal, the classification entry in `GET /log` shows `status: under_review` and `appeal_reasoning` populated.

## Project structure

```
app.py                  # Flask routes + rate limiting
config.py               # Settings, rate limits, paths
audit.py                # JSONL audit log + submission store
scoring.py              # Confidence fusion + label mapping
signals/
  llm_classifier.py     # Signal 1 — Groq LLM
  stylometrics.py       # Signal 2 — burstiness + punctuation entropy
test_milestone4.py
test_milestone5.py
planning.md
logs/audit.jsonl        # Runtime audit trail (gitignored)
```

## Status

- [x] Milestone 1 — Architecture
- [x] Milestone 2 — Spec
- [x] Milestone 3 — `POST /submit` + Signal 1 + audit log
- [x] Milestone 4 — Signal 2 + confidence fusion
- [x] Milestone 5 — Labels + appeals + rate limiting + complete audit log
