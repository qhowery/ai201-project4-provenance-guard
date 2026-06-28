# Provenance Guard — AI201 Project 4

**Student:** Quonlee Howery · qhowery@princeton.edu

Provenance Guard is a backend service for creative platforms that need to classify whether submitted text was likely AI-generated or human-written, surface a **transparency label** to users, log every decision for audit, and let creators **appeal** misclassifications.

---

## Architecture

A submission enters through `POST /submit` and passes through a two-signal detection pipeline before a label is returned.

```
POST /submit (text, creator_id)
    → Signal 1: LLM classifier (Groq)     → llm_score
    → Signal 2: Stylometric heuristics    → stylo_score
    → Confidence scorer (60/40 fusion + divergence check) → final_score
    → Label mapper (5 internal tiers → 3 external labels) → attribution text
    → Audit log (JSONL) + response

POST /appeal (content_id, creator_id, creator_reasoning)
    → Verify submitter → status: under_review → audit log entry
```

**Design principle:** No single signal is trusted alone. The LLM captures semantic/style patterns; stylometrics captures structural regularity. When they disagree sharply (`|llm − stylo| > 0.40`), the system forces an **uncertain** outcome rather than overconfidently flagging a human writer.

**Storage:** Classifications persist in `logs/audit.jsonl` (append-only JSON lines) plus an in-memory index for appeal lookups. A production deployment would use a database; JSONL keeps the audit trail human-readable for this project.

See `planning.md` for the full spec and ASCII flow diagrams.

---

## Detection signals

### Why two signals?

AI detection is unreliable with any single method. LLMs can be fooled by edited AI output; heuristics misfire on formal human prose. Combining complementary signals — one semantic, one statistical — lets the system hedge when evidence conflicts.

### Signal 1 — LLM classifier (Groq `llama-3.3-70b-versatile`)

**What it measures:** Holistic authorship style — word choice originality, filler phrases ("It is important to note…"), tone flatness, and paragraph predictability.

**Why this signal:** LLMs are good at recognizing other LLM writing patterns because they were trained on similar text. A structured JSON prompt returns a calibrated `llm_score` ∈ [0.0, 1.0].

**Blind spot:** Heavily edited AI passes as human; formal academic human writing triggers AI-like patterns. The model only sees final text, not the writing process.

**If deploying for real:** I'd fine-tune a smaller classifier on labeled human/AI pairs from the target platform's genre, rather than relying on a general-purpose LLM judge. I'd also log prompt versions for reproducibility.

### Signal 2 — Stylometric heuristics (pure Python)

**What it measures:**
- **Burstiness** — coefficient of variation of sentence lengths (humans vary rhythm; AI tends toward uniform sentences)
- **Punctuation entropy** — Shannon entropy over mark types (humans use messier punctuation mixes)

Combined: `stylo_score = 0.55 × burst_ai + 0.45 × punct_ai`

**Why this signal:** Structural tells are cheap, deterministic, and don't require an API call. They catch polished uniform prose even when an LLM classifier hesitates.

**Blind spot:** Short texts (<3 sentences) return neutral 0.50. Formal journalism and legal writing are intentionally uniform — low burstiness doesn't mean AI.

**If deploying for real:** I'd add genre detection first and apply different stylometric baselines per genre (poetry vs. essay vs. fiction).

---

## Confidence scoring

### Approach

1. **Weighted fusion:** `final_score = 0.60 × llm_score + 0.40 × stylo_score` (LLM weighted higher because it captures meaning-level tells)
2. **Divergence override:** if `|llm − stylo| > 0.40` → force `final_score = 0.50` (uncertain band)
3. **Five internal tiers** mapped to **three external labels** (symmetric thresholds around 0.5 — see `planning.md`)

Confidence is an **AI-likelihood score**, not "probability we're correct." A score of 0.60 means the text leans AI-ward on our scale, not that we're 60% sure.

### Example submissions (from `test_milestone4.py` → `TEST_CASES`)

These are the **same texts** used in automated Milestone 4/5 tests — not ad-hoc copy.

#### High-confidence human — casual review (`confidence: ~0.22`)

**Text:** *"ok so i finally tried that new ramen place downtown and honestly? underwhelming. the broth was fine but they put WAY too much sodium in it..."*

| Signal | Score (typical live run) |
|--------|--------------------------|
| `llm_score` | ~0.23 |
| `stylo_score` | ~0.22 |
| `divergence` | ~0.01 |
| **`final_score`** | **~0.22** |

**Label:** `high-confidence human`  
**Attribution:** *"This content was assessed as human-written (22% confidence)."*

Both signals agree: informal tone, irregular sentence lengths, casual punctuation. **Human agreement rule:** when both signals are below 0.30 and divergence is low, label high-confidence human even though the fused score is above 0.18.

---

#### Uncertain — AI boilerplate with signal conflict (`confidence: 0.500`, forced)

**Text:** *"Artificial intelligence represents a transformative paradigm shift... It is important to note that while the benefits of AI are numerous... Furthermore, stakeholders across various sectors must collaborate..."*

| Signal | Score |
|--------|-------|
| `llm_score` | 0.920 |
| `stylo_score` | 0.318 |
| `divergence` | 0.602 |
| **`final_score`** | **0.500** *(divergence override)* |

**Label:** `uncertain`  
**Attribution:** *"This content could not be confidently attributed (50% confidence). Attribution is uncertain."*

The LLM sees obvious AI filler phrases, but stylometrics finds moderate burstiness (mixed sentence lengths). Signals conflict → system refuses a high-confidence AI label. This is intentional: over-flagging is worse than hedging.

*(When both signals agree high — e.g., llm=0.90, stylo=0.85 — final_score reaches ~0.88 → `high-confidence AI`.)*

---

## Transparency labels

Three variants. The **`label`** field is the short badge; **`attribution`** is the user-facing sentence.

### Variant 1 — high-confidence AI
- **When:** `final_score ≥ 0.82`
- **Label:** `high-confidence AI`
- **Exact text:** `This content was assessed as AI-generated ({pct}% confidence).`
- **Example:** `This content was assessed as AI-generated (88% confidence).`

### Variant 2 — high-confidence human
- **When:** `final_score < 0.18`, **or** both `llm_score` and `stylo_score` `< 0.30` (with no divergence override)
- **Label:** `high-confidence human`
- **Exact text:** `This content was assessed as human-written ({pct}% confidence).`
- **Example:** `This content was assessed as human-written (22% confidence).`

### Variant 3 — uncertain
- **When:** scores in the middle band, or divergence override fired
- **Label:** `uncertain`
- **Exact text:** `This content could not be confidently attributed ({pct}% confidence). Attribution is uncertain.`
- **Example:** `This content could not be confidently attributed (50% confidence). Attribution is uncertain.`

---

## Appeals workflow

Creators who believe they were misclassified can appeal via `POST /appeal`:

```json
{
  "content_id": "uuid-from-submit-response",
  "creator_id": "must-match-original-submitter",
  "creator_reasoning": "min 20 characters explaining why the label is wrong"
}
```

The system verifies the submitter, sets status to `under_review`, and appends an appeal entry to the audit log with the original scores preserved. No automated re-classification — a human reviewer would use `GET /log` to inspect the full provenance chain.

---

## Rate limiting

`POST /submit` is limited to **`10 per minute; 100 per day`** per IP (Flask-Limiter, in-memory storage).

| Limit | Rationale |
|-------|-----------|
| 10/min | A writer revising drafts might submit several times; blocks scripted flooding |
| 100/day | Generous for legitimate daily use; stops sustained abuse |

**Verified behavior** (12 rapid requests):
```
200 200 200 200 200 200 200 200 200 200 429 429
```

---

## Audit log sample

```json
{
  "event_type": "classification",
  "content_id": "e2c1c8f5-c060-4cc1-9ecf-d32db38e90c9",
  "creator_id": "writer-1",
  "timestamp": "2026-06-27T12:46:50.381593Z",
  "llm_score": 0.90,
  "stylo_score": 0.318,
  "confidence": 0.5,
  "divergence": 0.602,
  "forced_uncertain": true,
  "internal_label": "uncertain_internal",
  "label": "uncertain",
  "attribution": "This content could not be confidently attributed (50% confidence). Attribution is uncertain.",
  "status": "under_review",
  "appeal_filed": true,
  "appeal_reasoning": "I wrote this myself from personal experience..."
}
```

---

## Known limitations

### Repetitive poetry with uniform line length

**Example:** *"We were tired. We were hungry. We were lost. We were alone."*

**Why it fails:** Stylometrics sees uniformly short sentences → low burstiness → high `burst_ai`. Punctuation is repetitive → low entropy → high `punct_ai`. If the LLM also reads the flat tone as AI-like, both signals agree on a false high-AI score with no divergence safety net.

**Root cause:** Burstiness assumes human writing varies sentence length; deliberate poetic repetition violates that assumption. This is a property of the stylometric signal, not a data volume problem.

**Mitigation in this system:** Appeals workflow — the creator explains the artistic intent; a reviewer overrides manually.

---

## Spec reflection

**How the spec helped:** Writing thresholds in `planning.md` before coding prevented a binary 0.5 flip. The five-tier internal mapping with three external labels was concrete enough to paste into AI prompts and verify against — when generated code used a single cutoff, I caught it immediately.

**Where implementation diverged:** The spec's appeal API example in the assignment curl omits `creator_id`, but my spec requires it for identity verification. I kept `creator_id` as required because without it any user could appeal any submission. I also store full submission text in the audit log (not just scores) to support human review — slightly more data than the minimal spec entry, but necessary for appeals to be actionable.

---

## AI tool usage

### Instance 1 — Flask skeleton + Signal 1 (Milestone 3)

- **What I gave the AI:** `planning.md` §1 (LLM signal contract), API contract for `POST /submit`, architecture diagram
- **What it produced:** Flask app structure, Groq API call with JSON parsing, basic audit log writer
- **What I revised:** Added regex fallback for LLM JSON parse failures; changed interim M3 attribution to Signal-1-only wording; added `ScoringError` exception instead of generic try/except returning 500

### Instance 2 — Stylometrics + confidence fusion (Milestone 4)

- **What I gave the AI:** §1 Signal 2 formulas, §2 uncertainty thresholds, `compute_confidence()` pseudocode
- **What it produced:** `score_stylometrics()` and `compute_confidence()` functions
- **What I revised:** Verified divergence threshold was exactly 0.40 (AI initially used 0.5); fixed sentence splitting to handle edge cases with no punctuation; added `<3 sentences → neutral 0.50` guard that the AI omitted

### Instance 3 — Appeals + rate limiting (Milestone 5)

- **What I gave the AI:** §4 appeals workflow, Flask-Limiter setup note from assignment, label variant strings
- **What it produced:** `POST /appeal` handler, limiter decorator, appeal audit entry structure
- **What I revised:** Added log hydration so appeals work after server restart; required `creator_id` on appeals; enriched `GET /log` to show `under_review` status on classification entries after appeal

---

## Setup & testing

```bash
cd ai201-project4-provenance-guard
pip install -r requirements.txt   # first time only — use project venv (see below)
cp .env.example .env            # add GROQ_API_KEY

# Start server (pick ONE — do NOT use bare `python app.py` unless which python points here)
./run.sh
# or: .venv/bin/python app.py
```

**Important:** If `python app.py` fails with `No module named 'flask'`, your shell is using the wrong Python. Use `./run.sh` or `.venv/bin/python app.py`.

First-time venv setup:
```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

```bash
# Submit
curl -s -X POST http://localhost:5000/submit \
  -H "Content-Type: application/json" \
  -d '{"text": "The sun dipped below the horizon, painting the sky in hues of amber and rose. I sat on the porch, coffee in hand, watching the neighborhood slowly go quiet.", "creator_id": "test-user-1"}' | python -m json.tool

# Appeal (paste content_id from above)
curl -s -X POST http://localhost:5000/appeal \
  -H "Content-Type: application/json" \
  -d '{"content_id": "PASTE-ID", "creator_id": "test-user-1", "creator_reasoning": "I wrote this myself from personal experience. I am a non-native English speaker and my writing style may appear more formal than typical."}' | python -m json.tool

# Audit log
curl -s http://localhost:5000/log | python -m json.tool

# Automated tests
python test_milestone4.py
python test_milestone5.py
```

## Demo video

See **`demo_notes.txt`** for a ~2-minute portfolio walkthrough script.

- [ ] Demo video link (add URL here when recorded)

## Project structure

```
app.py                  # Flask routes + rate limiting
config.py               # Settings, rate limits
audit.py                # JSONL audit log + submission store
scoring.py              # Confidence fusion + label mapping
signals/
  llm_classifier.py     # Signal 1 — Groq LLM
  stylometrics.py       # Signal 2 — burstiness + punctuation entropy
test_milestone4.py      # 4-input scoring tests
test_milestone5.py      # Labels, appeals, rate limit tests
planning.md             # Full architecture spec
demo_notes.txt          # Video script
logs/audit.jsonl        # Runtime audit trail (gitignored)
```

## Submission checklist

- [x] Architecture explained with design reasoning
- [x] Detection signals — why chosen, blind spots, production changes
- [x] Confidence scoring — two example submissions with actual scores
- [x] Three label variants — exact text written out
- [x] Appeals workflow documented
- [x] Rate limiting — limits, rationale, 429 evidence
- [x] Audit log sample
- [x] Known limitations — specific failure case tied to signal property
- [x] Spec reflection
- [x] AI usage — 3 instances documented
- [ ] Demo video recorded and linked
