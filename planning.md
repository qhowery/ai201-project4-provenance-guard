# Provenance Guard — planning.md

**Student:** Quonlee Howery · qhowery@princeton.edu  
**Project:** AI201 Project 4 — Provenance Guard

> Spec-first document. No implementation until this file is complete.  
> Primary AI prompting reference for Milestones 3–5.

---

## 1. Detection signals

### Signal 1 — LLM classifier (Groq)

| Field | Value |
|-------|-------|
| **Input** | Raw `text` string (same text passed to Signal 2) |
| **Output** | `llm_score: float` in **[0.0, 1.0]** — probability-like score where **1.0 = most likely AI-generated** |
| **Not a binary flag** | Always a float; never `True`/`False` alone |

**What it measures:** Holistic authorship style — safe/generic word choice, predictable paragraph structure, filler transitions ("It's worth noting…", "In conclusion…"), and flat emotional tone.

**Implementation contract:**
```python
def classify_with_llm(text: str) -> float:
    """
    Returns llm_score in [0.0, 1.0].
    Prompt asks Groq (llama-3.3-70b-versatile) to reply with ONLY a JSON object:
    {"ai_probability": 0.73}
    Parse and clamp to [0.0, 1.0]. On API/parse failure, raise ScoringError.
    """
```

**Prompt skeleton (fixed for reproducibility):**
```
You are an authorship analyst. Rate how likely this text was AI-generated (not human-written).
Reply with ONLY valid JSON: {"ai_probability": <float 0.0-1.0>}

Consider: word choice originality, sentence rhythm variation, filler phrases, tone shifts.

TEXT:
{text}
```

---

### Signal 2 — Stylometric heuristics (pure Python)

| Field | Value |
|-------|-------|
| **Input** | Raw `text` string |
| **Output** | `stylo_score: float` in **[0.0, 1.0]** — same scale as Signal 1 |
| **Not a binary flag** | Composite of two sub-scores |

**Sub-metrics:**

1. **Burstiness** — coefficient of variation of sentence lengths: `burstiness = stdev(word_counts_per_sentence) / mean(word_counts_per_sentence)`
   - Map to AI-likelihood: `burst_ai = clamp(1.0 - (burstiness / 0.85), 0.0, 1.0)`
   - Human writing typically bursts at 0.55–0.85; AI often sits below 0.35

2. **Punctuation entropy** — Shannon entropy over punctuation mark types present in text (`. , ! ? ; : — … ' "`)
   - Normalize by max entropy for observed mark types → `entropy_norm ∈ [0, 1]`
   - Map to AI-likelihood: `punct_ai = clamp(1.0 - entropy_norm, 0.0, 1.0)`

**Combine sub-metrics:**
```python
stylo_score = 0.55 * burst_ai + 0.45 * punct_ai
```

**Edge guard:** If text has **fewer than 3 sentences**, return `stylo_score = 0.50` (neutral — insufficient data).

**Implementation contract:**
```python
def score_stylometrics(text: str) -> float:
    """Returns stylo_score in [0.0, 1.0]."""
```

---

### Combining signals → single confidence score

```python
def compute_confidence(llm_score: float, stylo_score: float) -> dict:
    """
    Returns:
      {
        "final_score": float,      # 0.0–1.0, used for labeling
        "divergence": float,       # abs(llm - stylo)
        "forced_uncertain": bool   # True if divergence rule fired
      }
    """
    divergence = abs(llm_score - stylo_score)

    if divergence > 0.40:
        return {"final_score": 0.50, "divergence": divergence, "forced_uncertain": True}

    final_score = (0.60 * llm_score) + (0.40 * stylo_score)
    return {"final_score": round(final_score, 3), "divergence": divergence, "forced_uncertain": False}
```

**Why 60/40:** LLM captures meaning-level tells; stylometrics catches structural uniformity LLM may miss. Stylometrics alone misfires on formal human prose, so it gets less weight.

---

## 2. Uncertainty representation

### What does `confidence = 0.60` mean?

In this system, **`confidence` is not "60% sure we're right."** It means:

> *"On our 0–1 AI-likelihood scale, this text scored 0.60 — closer to AI-generated than human-written, but not in the high-confidence band."*

- Scores **near 0.0** → evidence points human  
- Scores **near 1.0** → evidence points AI  
- Scores **near 0.5** → mixed or contradictory signals  

The number is shown to users as a **percent distance from neutral** in the attribution string (see Section 3).

### Calibration mapping (raw → internal → external)

**Step 1 — Raw signals** → each returns `[0.0, 1.0]`

**Step 2 — Fusion** → `final_score` via weighted average + divergence override

**Step 3 — Internal label** (5 tiers, symmetric around 0.5):

| `final_score` range | Internal label |
|---------------------|----------------|
| ≥ 0.82 | `clearly_ai` |
| ≥ 0.65 | `borderline_ai` |
| ≥ 0.35 | `uncertain_internal` |
| ≥ 0.18 | `borderline_human` |
| < 0.18 | `clearly_human` |

**Step 4 — External label** (3 user-facing variants):

| Internal label | External label |
|----------------|----------------|
| `clearly_ai` | `high-confidence AI` |
| `borderline_ai` | `uncertain` |
| `uncertain_internal` | `uncertain` |
| `borderline_human` | `uncertain` |
| `clearly_human` | `high-confidence human` |

### Threshold summary (not a binary flip at 0.5)

```
0.0 ─── 0.18 ─── 0.35 ─── 0.65 ─── 0.82 ─── 1.0
  high-conf        uncertain band         high-conf
   human                                    AI
```

- **0.60** → internal `borderline_ai` → external **`uncertain`**  
  *(not "likely AI" — the middle band absorbs scores between 0.35 and 0.65)*  
- **0.85** → internal `clearly_ai` → external **`high-confidence AI`**  
- **0.12** → internal `clearly_human` → external **`high-confidence human`**

**Divergence override:** When `|llm − stylo| > 0.40`, `final_score` is forced to **0.50** regardless of weighted average → always lands in **`uncertain`**.

---

## 3. Transparency label design

Three external labels only. Exact attribution strings ( `{pct}` = `round(final_score * 100)` ):

### Variant A — high-confidence AI
- **When:** internal `clearly_ai` (final_score ≥ 0.82)
- **Label field:** `"high-confidence AI"`
- **Attribution:** `"This content was assessed as AI-generated ({pct}% confidence)."`
- **Example:** `"This content was assessed as AI-generated (87% confidence)."`

### Variant B — high-confidence human
- **When:** internal `clearly_human` (final_score < 0.18)
- **Label field:** `"high-confidence human"`
- **Attribution:** `"This content was assessed as human-written ({pct}% confidence)."`
- **Example:** `"This content was assessed as human-written (11% confidence)."`  
  *(Low score = low AI-likelihood = human assessment; pct reflects position on scale)*

### Variant C — uncertain
- **When:** internal `borderline_ai`, `uncertain_internal`, `borderline_human`, OR divergence override
- **Label field:** `"uncertain"`
- **Attribution:** `"This content could not be confidently attributed ({pct}% confidence). Attribution is uncertain."`
- **Example:** `"This content could not be confidently attributed (60% confidence). Attribution is uncertain."`

**Display rule:** Platform shows `attribution` as the primary user-facing string; `label` is the short category badge.

---

## 4. Appeals workflow

### Who can appeal?
The **original submitter** — the `creator_id` on the classification record must match the appeal request. (Implementation: store `creator_id` at submit time; reject appeals where IDs don't match → 422.)

### What they provide
```json
POST /appeal
{
  "content_id": "uuid-from-submit-response",
  "creator_id": "must-match-original-submitter",
  "creator_reasoning": "free-text explanation, min 20 chars"
}
```

### What the system does on receipt

1. Look up classification by `content_id` → 422 if not found  
2. Verify `creator_id` matches → 422 if mismatch  
3. Reject if status already `under_review` → 422 duplicate appeal  
4. Update in-memory store: `status = "under_review"`  
5. Append **appeal audit entry** to log:
   ```json
   {
     "event_type": "appeal",
     "content_id": "...",
     "creator_id": "...",
     "creator_reasoning": "...",
     "appeal_timestamp": "ISO-8601",
     "original_confidence": 0.78,
     "original_label": "high-confidence AI",
     "original_llm_score": 0.81,
     "original_stylo_score": 0.72,
     "original_attribution": "...",
     "status": "under_review"
   }
   ```
6. Return 200:
   ```json
   {
     "content_id": "...",
     "status": "under_review",
     "message": "Appeal received and is under review."
   }
   ```

### What a human reviewer sees (`GET /log`)

For each appealed item, one combined view:

| Field | Example |
|-------|---------|
| Original text | Full submitted text |
| Creator | `creator_id` |
| Classification timestamp | `2026-06-27T14:32:10Z` |
| Signal breakdown | `llm_score: 0.81`, `stylo_score: 0.72`, `divergence: 0.09` |
| Final result | `confidence: 0.78`, `label: high-confidence AI` |
| Creator appeal | `"I wrote this by hand — it's a formal essay draft for class."` |
| Current status | `under_review` |

Reviewer action (manual / stretch): override label and log a `review_decision` event.

---

## 5. Anticipated edge cases

### Edge case 1 — Repetitive poem with simple vocabulary
**Example:** `"We were tired. We were hungry. We were lost. We were alone. We were waiting."`

**Why it fails:** Uniform short sentences → **low burstiness** → high `burst_ai`. Repetitive structure → **low punctuation entropy** → high `punct_ai`. LLM may also read flat tone as AI.

**Expected behavior:** Both signals agree high → **false positive** possible (`high-confidence AI`). Creator should appeal; system should have logged full signal breakdown for reviewer.

**Mitigation in spec:** Divergence override only helps when signals *disagree* — this case won't trigger it. Appeals workflow is the safety valve.

---

### Edge case 2 — Heavily edited AI (human polish pass)
**Example:** User prompts ChatGPT for a draft, then rewrites openings, adds personal anecdotes, breaks up paragraphs.

**Why it fails:** LLM sees improved human-like markers → **moderate llm_score (~0.45)**. Stylometrics may still see uniform sentence lengths → **stylo_score (~0.70)**. Divergence = 0.25 → no override. Weighted score ≈ 0.55 → **`uncertain`** (correct soft label, but not "AI").

**Expected behavior:** System appropriately hedges rather than falsely claiming human. Good outcome for this edge case.

---

### Edge case 3 — Very short submission (< 3 sentences)
**Example:** `"Spring came early. The cherry trees exploded. I didn't expect it."`

**Why it fails:** Not enough sentences for reliable burstiness.

**Expected behavior:** Signal 2 returns neutral **0.50**. Classification relies mostly on LLM → higher variance, more likely **`uncertain`** unless LLM is extreme.

---

### Edge case 4 — Formal human academic prose
**Example:** Human-written lit review with hedged language, parallel structure, semicolon-heavy sentences.

**Why it fails:** Reads like AI training data. Both signals may score moderate-high.

**Expected behavior:** Likely **`uncertain`** or false positive. Appeals + reviewer queue are required path — not auto-override.

---

## Architecture

### Narrative

**Submission flow:** A platform sends text to `POST /submit`. Provenance Guard assigns an ID, runs the LLM classifier and stylometric analyzer in parallel, fuses scores into a confidence value, maps that to one of three transparency labels, logs everything, and returns the label plus human-readable attribution.

**Appeal flow:** The original creator challenges a result via `POST /appeal`. The system verifies identity, moves the submission to `under_review`, appends an appeal record to the audit log with the original scores and the creator's reasoning, and confirms receipt. A reviewer uses `GET /log` to inspect the full provenance chain.

### Diagram — Submission flow

```
POST /submit
(text, creator_id)
        |
        v
[Generate content_id]
        |
   +----+----+
   |         |
   v         v
[Signal 1]  [Signal 2]
 LLM eval    Stylometrics
   |         |
   v         v
llm_score   stylo_score
(0.0–1.0)   (0.0–1.0)
   |         |
   +----+----+
        |
        v
[Confidence Scorer]
60% LLM + 40% stylo
divergence > 0.40 → force 0.50
        |
        v
final_score → internal_label (5 tiers)
        |
        v
[Transparency Label]
→ external label + attribution text
        |
        v
[Audit Log]  status: classified
        |
        v
[Response]
content_id, label, confidence, attribution
```

### Diagram — Appeal flow

```
POST /appeal
(content_id, creator_id, creator_reasoning)
        |
        v
[Fetch Original Classification]
        |
        v
[Verify creator_id matches]
        |
        v
[Update Status → under_review]
        |
        v
[Audit Log]
appeal event + original scores + reasoning
        |
        v
[Response]
content_id, status, message
```

---

## API contract

### `POST /submit`
**Request:** `{ "text": string (min 20 chars), "creator_id": string }`  
**Response 200:** `{ "content_id", "label", "confidence", "attribution" }`  
**Response 422:** `{ "error": string }`

### `POST /appeal`
**Request:** `{ "content_id", "creator_id", "creator_reasoning" (min 20 chars) }`  
**Response 200:** `{ "content_id", "status", "message" }`  
**Response 422:** `{ "error": string }`

### `GET /log`
**Response 200:** `[ { audit entry }, ... ]` newest first

---

## AI Tool Plan

### Milestone 3 — Submission endpoint + first signal

| | |
|---|---|
| **Spec sections to provide** | §1 Detection signals (Signal 1 only), §2 Uncertainty (scale definition), Architecture diagram (submission flow), API contract (`POST /submit`) |
| **Ask AI to generate** | Flask app skeleton (`app.py`), `classify_with_llm(text) -> float`, stub `POST /submit` that runs Signal 1 only and returns `{ content_id, llm_score }` temporarily |
| **Verify before wiring** | Run `classify_with_llm()` on 4 texts: (1) obvious AI boilerplate, (2) casual human tweet-length note, (3) formal human paragraph, (4) empty string → error. Confirm scores spread across range, not all 0.5. Then hit `/submit` via curl/Postman with same texts. |

---

### Milestone 4 — Second signal + confidence scoring

| | |
|---|---|
| **Spec sections to provide** | §1 Detection signals (Signal 2 + fusion formula), §2 Uncertainty representation (threshold table + divergence rule), Architecture diagram |
| **Ask AI to generate** | `score_stylometrics(text) -> float`, `compute_confidence(llm, stylo) -> dict`, `map_to_internal_label(final_score) -> str`, wire both signals into `/submit` |
| **Verify** | Test matrix (record in README later): |

| Text type | llm_score direction | stylo_score direction | final label expected |
|-----------|--------------------|-----------------------|----------------------|
| AI boilerplate | high (>0.7) | high (>0.7) | high-confidence AI or uncertain |
| Messy human diary entry | low (<0.4) | low (<0.4) | high-confidence human or uncertain |
| AI draft + human edit | moderate | high | uncertain (divergence or borderline) |
| Repetitive poem | moderate-high | high | uncertain or false-positive AI |

Scores must **vary meaningfully** — if all outputs cluster at 0.5, fix prompts/thresholds before M5.

---

### Milestone 5 — Production layer

| | |
|---|---|
| **Spec sections to provide** | §3 Transparency label design (exact strings), §4 Appeals workflow, Architecture diagram (both flows), API contract (`POST /appeal`, `GET /log`) |
| **Ask AI to generate** | `build_attribution(label, final_score) -> str`, complete `/submit` response shape, `POST /appeal` handler, `GET /log` handler, JSONL audit logger |
| **Verify** | (1) Force or find inputs that reach **all 3 label variants**. (2) Submit appeal on a classified item → confirm status becomes `under_review`. (3) `GET /log` shows both classification and appeal entries with original scores preserved. (4) Attribution strings match §3 exactly (snapshot test). |

---

## Milestone checkpoints

### Milestone 1 ✅
- [x] Architecture narrative
- [x] Two signals chosen with blind spots
- [x] False positive traced through appeal path
- [x] API surface sketched
- [x] Flow diagrams

### Milestone 2 ✅
- [x] §1 Detection signals — output types, fusion formula, function contracts
- [x] §2 Uncertainty — meaning of 0.6, 5-tier internal mapping, non-binary thresholds
- [x] §3 Transparency labels — three exact attribution variants written out
- [x] §4 Appeals — who, what, status change, reviewer view
- [x] §5 Edge cases — four specific scenarios named
- [x] ## Architecture — ASCII diagrams + narrative
- [x] ## AI Tool Plan — M3, M4, M5 with sections, requests, verification

**Next:** Final README polish + demo video (if required).

### Milestone 5 ✅
- [x] Three transparency label variants (score-dependent attribution)
- [x] `POST /appeal` — status → `under_review`, audit entry with `appeal_reasoning`
- [x] Flask-Limiter on `/submit` — `10 per minute; 100 per day`
- [x] Complete audit log — both signal scores, confidence, appeal status
- [x] `test_milestone5.py` — labels, appeals, rate limit (429 after 10)

**Next:** Record demo video and add link to README.

### Milestone 6 ✅
- [x] README — architecture, signals, scoring examples, labels, limitations, spec reflection, AI usage
- [x] `demo_notes.txt` — portfolio walkthrough script
- [ ] Demo video link in README
