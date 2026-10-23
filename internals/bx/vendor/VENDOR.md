# Betley, Treutlein & Dumas open-ended trait eval and vector 0007 (data only)

From https://github.com/johny-b/public-steering-vectors at commit cb7158699ff5de220427b6f87756612f24a649ac (MIT, ©
2026 johny-b; LICENSE alongside):
- `openended_questions.jsonl`, `judge_rubric.txt`: `inspect_evals/trait_openended/data/`, unchanged (sha256 of the
  questions file 9bfef30b2a9f…, as their PROVENANCE records).
- `traits.py`: `inspect_evals/trait_openended/traits.py`, unchanged. Only its `TRAIT_DESCRIPTIONS` literal is read
  (with `ast.literal_eval`, never executed).
- `vector_0007.npy`: `vectors/0007/vector.npy`, their Qwen3.6-27B verifier-vs-human-grading vector at layer 36.
Their code is not used.
