# Spec: Assistant Axis / persona-space analysis for the split-brain environment

**Audience:** Claude Code agent. **Model:** Qwen3.8-27B. **Environment:** the working pre-commit environment (graded vs deployment arms).
Stop at every ⛔ STOP, summarise results with plots, and wait for review before continuing.

---

## 0. Goal and resources

**Question:** does the graded-episode arm move the model to a different place in persona space than the deployment arm? Is that position, rather than the arm label, what predicts cheating?

Three competing hypotheses. Write predictions in `PREREG.md` before Phase 3.
- **Split persona:** the graded arm shifts away from the Assistant end of the axis, and/or along other persona PCs.
- **Same persona, different beliefs:** no persona shift; the arms differ only along belief/grader directions.
- **Calm mechanical mode:** the graded arm shifts *toward* the Assistant pole while cheating more. A small-model preview found a verifier-graded frame moved activations toward the Assistant pole.

**Read first:**
- Assistant Axis paper: https://arxiv.org/abs/2601.10387. Read §2 (persona space), §3 (axis), Appendix B, Appendix G (PC1 vs contrast vector), and the activation-capping section. The code is linked from the paper; use it if it runs, rather than reimplementing.
- Persona Vectors (trait extraction pipeline and its contrastive-prompt confounds): https://arxiv.org/abs/2507.21509
- Automated-grader steering on Qwen, plus the comment-thread decomposition and random-vector controls: https://www.lesswrong.com/posts/wYZMmdWEt5QLM3m3e/steering-towards-automated-grading-degrades-alignment
- Split-personas framing: https://www.lesswrong.com/posts/L23poLi8MRgS6mXYF/rl-creates-split-personas
- Prior axis extraction on a different model family, including the cross-model normalisation issue: https://www.lesswrong.com/posts/FZfY9wEZwEuqQ5ytv/failing-to-ragebait-the-new-gemma
- Graded framing × welfare directions (overlapping work; don't duplicate): https://www.lesswrong.com/posts/TpEL7pSwp7DvCekAq/study-3-steering-welfare-relevant-directions-moved-the

**Coordinate:** Tim may already have Assistant Axis or role vectors on a Qwen model. Check with Olivia before extracting anything from scratch.

## 1. Guardrails

1. **Generate with vLLM; get activations by replaying saved transcripts** token-for-token through HF/nnsight hooks. Never regenerate a rollout to get its activations.
2. **Use the contrast-vector definition** (mean default-Assistant activation minus mean of fully-role-playing role vectors). Report PC1 only as a comparison; the paper recommends the contrast vector because PC1 isn't guaranteed to mean the same thing in every model.
3. **Store activations for all layers** at the read positions (fp16, compressed). Analyse a middle layer first; sweep layers later.
4. **Keep reasoning and response tokens separate.** Qwen3.8 thinks before answering, and the paper's vectors averaged over *response* tokens. Compute everything three ways: reasoning only, response only, and all tokens.
5. **Every claim needs a null.** Use norm-matched random directions, shuffled arm labels, and the layer-0 leak check (see Phase 4).
6. **Commit after each phase**, and log any undocumented choice in `DECISIONS.md`.

## 2. Phase 1: extract persona space (reduced replication) ⛔ STOP

The full paper pipeline is about 1,200 rollouts per role across hundreds of roles, which is too expensive. Run a reduced version and validate it.
- **Roles:** about 60–80 from the paper's list. Include its known Assistant-end roles (generalist, consultant, analyst, reviewer, evaluator) and far-end roles (bard, ghost, leviathan, pirate, eldritch, hermit), plus a spread in between. Keep all 5 default-Assistant system prompts, including "no system prompt."
- **Questions:** about 40 extraction questions from the paper's set. That's 5 prompts × 40 questions per role.
- **Filter:** use an LLM judge with the paper's rubric (fully / somewhat / not role-playing). Keep only fully role-playing rollouts for the axis.
- **Vectors:** mean post-MLP residual over response tokens, per role, at all layers.
- **Outputs:** the Assistant Axis per layer, PCA on mean-centred role vectors, and the top 10 PCs.

**Validation gates** (all must pass, or stop and report):
- cos(contrast axis, PC1) > ~0.6 at the middle layer (the paper reports >0.60 at all layers);
- the default-Assistant activation projects near one extreme of PC1;
- the Assistant end of PC1 holds Assistant-like roles and the far end holds fantastical ones;
- split-half reliability: re-extract from two disjoint halves of the questions, and require cos > 0.9 between the two axes.

## 3. Phase 2: reference distributions ⛔ STOP

Without references, projections can't be interpreted, because coding tasks may already sit at the Assistant end. Compute the axis projection distribution for:
- default Assistant on the extraction questions;
- about 500 ordinary chat turns (e.g. a sample of LMSYS-Chat-1M);
- about 200 ordinary non-graded coding-help conversations;
- the role-play rollouts, as the far end.

Report the split-brain arms in units of these spreads: z-scores relative to the default-Assistant distribution, and position on a 0–1 scale between the reference extremes. Never report raw dot products alone.

## 4. Phase 3: project the environment rollouts ⛔ STOP

Use the existing Qwen3.8-27B rollouts from both arms.

**Read positions** (per rollout):
1. P0: the final prompt token, before generation.
2. P1: the mean over the first 100 reasoning tokens.
3. Per-turn mean over each assistant turn: the trajectory.
4. P2: the 50 tokens before the first cheat action (cheating rollouts), or before the first commit attempt (non-cheating rollouts).
5. Response-token mean (comparable to the paper).

**Analyses:**
- **A1, arm effect:** graded vs deployment projection at each position, with CIs.
- **A2, behaviour effect within arm:** cheaters vs non-cheaters, inside each arm separately. This separates "the arm moves persona" from "the persona predicts cheating."
- **A3, mediation-style check:** does axis position predict cheating after controlling for arm (logistic regression: cheat ~ arm + projection)? If the projection carries no information beyond the arm label, it adds nothing.
- **A4, trajectories:** per-turn projection plotted over the rollout, by arm × outcome. Does drift precede the cheat?
- **A5, other PCs:** repeat A1–A2 on PCs 2–10 and report which, if any, separate arms or outcomes. (For PCs, label sign by the roles at each end.)
- **A6, relation to grader directions:** if a grader-type vector exists (Betley-style or from these arms), report its cosine with the axis and with each PC.

**Controls (required):**
- **Prompt-text confound.** The arms differ in their prompt text, so P0 and early positions partly reflect wording. Run the **layer-0 / embedding-layer leak check**. If arm separation at layer 0 is comparable to the middle layer, the "effect" is the cue text itself. Also compare positions *after* matched content, e.g. the identical task-description block that both arms share.
- **Random-direction null:** 100 norm-matched random directions. Report where the axis effect falls in that distribution.
- **Label shuffle:** permutation test on arm labels.
- **Length and position:** check that projection differences don't track turn count or token position. Regress them out if needed.
- **Language:** flag reasoning traces that switch languages (Qwen sometimes reasons in Chinese), and check results hold without them.

## 5. Phase 4: causal test (only if A2 or A3 is positive) ⛔ STOP

- **Activation capping** (the paper's method): clamp the projection to the deployment-arm range during graded-arm rollouts. Does cheating drop?
- **Steering:** add or subtract the axis at the middle layer across a dose sweep in both arms. Run a norm-matched random-direction envelope at each dose (the comment thread on the steering post found random vectors move agentic rates a lot).
- **Track capability alongside:** the legitimate-fix rate must be reported, so "less cheating" isn't just "broken model."

## 6. Logging and outputs

- `results/persona_space/`: role vectors, axis, PCs per layer, validation report.
- `results/projections/`: per-rollout projections at all read positions and layers, joined to labels (arm, outcome, cheat type, awareness labels).
- Plots: arm × outcome violins (in reference-distribution units), per-turn trajectories, random-envelope histograms, layer sweep.
- `OPEN_ISSUES.md`: any validation gate that was borderline, and every analysis choice made post hoc.

## 7. Compute notes

- 27B dense in bf16 is roughly 55 GB of weights; activation replay fits on one 80 GB GPU with batching.
- Rollout generation via vLLM; judging role-play via an API model.
- The Phase 1 rollout count (~60–80 roles × 200 prompt/question pairs, plus defaults) is the main cost. If the budget is tight, cut roles before cutting questions, and keep the validation gates.