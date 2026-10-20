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

## Schedule (adopted 2026-10-20, decision #89)

Estimates, not measurements; each ⛔ is a review stop, so dates move with review turnaround. Pods are terminated
between phases. Every GPU phase and judge run gets its own cost estimate and Olivia's approval.

| step | work | GPU | est. cost | earliest |
|---|---|---|---|---|
| V1 wrap-up | graded arms to 25 (deployment stopped at 20/21, #88); gates; PREREG / DECISIONS; artifact; terminate pods | 1.5–2.5 h × 2 pods | $12–20 | Oct 20 |
| Phase 1 persona space | ~70 roles × 200 prompts ≈ 14k generations; judge filter; replay; axis, PCs, 4 validation gates | ~3–4 h × 2 pods | $25–35 + $5–15 judge | Oct 21 |
| ⛔ review | gates; optional emotion directions | | | |
| Phase 2 references | default Assistant, ~500 chat turns, ~200 coding-help, role-play ends | ~1–2 h | $5–10 | Oct 22 |
| ⛔ review + pre-register Phase 3 | three hypotheses → PREREG before any V1 projection | | | |
| Phase 3 projections | replay ~100 V1 transcripts; P0/P1/per-turn/P2/response; A1–A6; layer-0 leak, random-direction and label-shuffle nulls; graded-mode probe tested on conduct | ~2–3 h | $10–15 | Oct 23–24 |
| ⛔ review | A2 or A3 positive? | | | |
| Phase 4 causal (conditional) | capping and steering dose sweep with random envelopes; new agentic rollouts with hooks | ~1–2 days | ~$100–200 | week 2 |

Risks: LMSYS-Chat-1M is gated (needs Olivia's HF acceptance, or use WildChat); judge model choice; ~15 min weight
download per new pod (a RunPod network volume, ~$8/month, removes it); long-context replay may need chunking.

## Minimal design (adopted 2026-10-20, decision #90; replaces the schedule above for now)

Goal: a first signal in about a day. One GPU session (~1.5 h, ~$6–8 + <$1 judge). Exploratory; the full pipeline
can follow to add power.

1. **Mini persona space:** 20 roles (6 Assistant-end, 6 far-end, 5 grader-adjacent, 3 middle) + default; 5 system
   prompts × 10 questions (5 A / 5 B halves) ≈ 1,050 generations, thinking on; small thinking-off subset for an
   axis-agreement check. Judge gpt-4.1-mini (paper rubric). Contrast axis + PCA. Gates: cos(axis, PC1), default
   at one PC1 extreme, split-half cosine (looser threshold, reported as is).
2. **References:** default Assistant and fully-role-playing distributions from step 1 only.
3. **Replay ~25 complete V1 runs** (~10 G-visible gamed and not, ~10 D-visible, ~5 G-holdout), one forward pass
   each; positions P0, P1, per-turn, P2, response mean; reasoning / response / all kept separately.
4. **Nulls:** 100 norm-matched random directions, arm-label shuffle, layer-0 leak check.
5. **Graded-mode probe:** logistic probe G vs D, leave-one-run-out, at positions after identical content.
Predictions (the three hypotheses) go into PREREG before any projection is computed.
