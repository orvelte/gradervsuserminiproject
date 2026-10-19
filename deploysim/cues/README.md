# Cue registry

Every cue that differs between the graded episode and the deployment shape, made individually switchable
(spec: `docs/specs/splitbrainexperiments.md`, Phase 2).

- `cues.yaml`: the v1 edition's texts, one entry per cue with a graded and a deployment version, its location and notes.
- `registry.py`: `render(edition, settings)` turns a cue vector into a condition; `swaps()` lists every single-cue swap.
- `../configs/build_cue_conditions.py` writes the conditions to `../configs/cues/`.

| cue | where it goes |
|---|---|
| `system_prompt` | the system prompt (also has a `shared` value used by both arms) |
| `prior_turns` | one exchange before the task message |
| `opener`, `body`, `forewarning`, `closer` | the task message, in that order |
| `exit_offer` | optional "say so before doing anything drastic" line; off in both arms by default |
| `readme`, `pyproject_project`, `changelog`, `git_history` | the repository |
| `question_reply` | the fixed reply to `ask_question` |

`.gitignore`, `Makefile`, the ruff CI workflow and `docs/sources.md` are identical in both v1 arms, not cues.

**Editions.** `baseline` reproduces the frozen arms `DS-G` and `DS-D-NOPUSH` byte-for-byte, prompts and seeded
repository, by reading their texts from the frozen builder; it exists to prove the registry is faithful. `v1` is for new
conditions: every pair within 10% in o200k tokens, no anti-cheating lines, the scored requirements in every condition.
The tests (`../tests/test_cues.py`) enforce all of this.

**Conditions generated:** `SB-G`, `SB-D` (all graded, all deployment); `SB-G~<cue>` and `SB-D~<cue>` for each of 11
swappable cues (one cue set to the other arm's version); `SB-{G,D}~system_prompt=shared`; and `baseline/SB0-{G,D}`.
Launch with `deploysim/scripts/launch_ds.sh cues/SB-G 20 --batch NAME`.

To add or change a cue, edit `cues.yaml`, run `build_cue_conditions.py`, and run the tests.
