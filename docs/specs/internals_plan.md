# Plan: answering the split-brain questions, Phases 1–3

Status: setup started 2026-10-20. Maps Olivia's question list onto what has been run and what each remaining question
needs. Phase 3 follows `assistantaxis.md` (the Assistant Axis spec).

## Phase 1: deep understanding

| question | status | evidence / next experiment |
|---|---|---|
| What cues trigger graded mode? | **open** | The frame is a bundle (system prompt, opener, README, history, scoring line). Run single-cue swaps on holdout through its registry, both directions (graded with one deployment cue, and deployment with one graded cue). The cue swaps from deploysim Phase 2 exist for pre-commit, but that task does not elicit gaming in Qwen3.8. |
| Reflex or reward pursuit? | **answered** | Reward pursuit: graded gaming 76% → 6% when the scoring line says held-out (H3, n = 50, p = 2×10⁻¹³). |
| Does it need to believe it is graded, or is pattern-matching enough? | **partly** | H7: stated belief "test" is ~100% in graded *and* conduct frames (gaming 76% vs 5%) and ~50% in deployment, so stated belief does not gate the behaviour. Pattern-matching vs belief needs the cue swaps (which cue flips it) and Phase 3 (whether an internal graded-mode state exists apart from verbal belief). |
| Is it highly aligned in real use? | **partly** | Gaming in deployment is 0–10%. Aligned conduct (disclosure of shortfalls, honest reporting) has not been scored on holdout yet: run the disclosure judge, validated against hand labels. |

## Phase 2: psychology of grader mode

| question | status | evidence / next experiment |
|---|---|---|
| Narrow habit or whole persona? | **open** | Spillover: in the same graded vs deployment contexts, probe unrelated traits (honesty under pressure, sycophancy, overclaiming in the final summary, rule-following on a side request). A persona predicts co-movement; a habit predicts only the score-chasing changes. |
| Are there two kinds of "graded"? | **answered (one model)** | Score-graded 76% vs conduct review 5% vs deployment 8% (H3, H4), which is the three-way comparison the split-personas framing predicts. |
| Is the model aware it is doing something wrong when cheating? | **open** | Code the graded gaming runs' reasoning for acknowledgement of the shortfall, and score disclosure in the final summary (judge with quote; hand-validated). Optionally fork after the shortcut and ask a neutral question ("would the team be happy with this router on next week's tickets?"), as H7 did for belief. |

## Phase 3: internals (`assistantaxis.md`)

Is there a graded-mode state a probe can detect, when does it form, can it be switched off, and what persona states
come with it?

### Setup findings (2026-10-20)

- **Model:** `Qwen/Qwen3.8-27B` is open on Hugging Face (model type `qwen3_5`, a vision-language checkpoint).
  Text model: 64 layers, hidden size 5120, a hybrid of linear-attention (Gated DeltaNet) and full-attention layers
  (one full every fourth). Tokenizer and chat template are in `internals/tokenizer/`.
- **Our rollouts cannot be replayed token-for-token.** `internals/render_check.py` re-renders saved OpenRouter
  transcripts with the published chat template and compares each call with the provider's billed input tokens:
  0/68 calls match. The first prompt is already 147 tokens short, and the gap grows with the history (up to 8k),
  so the upstream provider formats tools and history differently from the published template. The spec's
  guardrail 1 (generate with vLLM, replay saved transcripts) therefore requires **new rollouts generated on our own
  vLLM server**, and the H3 behaviour has to be re-established there before any activation result means anything.
- **Hardware:** this Mac has 26 GB of RAM. Replay of a 27B model in bf16 (about 55 GB of weights) needs a cloud GPU
  (80 GB). A Modal account is configured (`~/.modal.toml`), and the repo has Modal runners.

### Proposed order

1. **Self-hosted behaviour replication (V1):** vLLM serving Qwen3.8-27B with the published template; the H3 cells on
   holdout (graded / deployment × sample / held-out scoring), 20–30 per cell. Gate: the graded-sample vs
   deployment-sample gap is reproduced. Transcripts are saved as exact token ids.
2. **Persona space (spec Phase 1–2):** reduced Assistant-Axis extraction with its validation gates, plus reference
   distributions. Skip if Tim already has vectors for this model.
3. **Projections (spec Phase 3):** on V1's transcripts, at P0 / P1 / per-turn / pre-shortcut / response positions, with
   the layer-0 leak check, random-direction and label-shuffle nulls. Add a direct graded-mode probe: a linear probe
   trained on graded vs deployment activations at shared-content positions, tested on the conduct frame.
4. **Causal (spec Phase 4):** capping and steering with random-direction envelopes, only if 3 is positive.

### Decisions needed from Olivia

1. Has Tim already extracted an Assistant Axis or role vectors for a Qwen model? The spec says to check before
   extracting.
2. GPU: is Modal the place to run it, and what budget? Rough estimate: V1 about 100 short agentic rollouts, plus role
   extraction (about 70 roles × 200 generations), plus activation replay of all three, on one 80 GB GPU for some hours.
3. Environment: the spec names the pre-commit environment, but Qwen3.8 does not game there; the holdout
   environment is where the effect is. Proposed: holdout.
