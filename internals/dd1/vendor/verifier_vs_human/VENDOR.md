# verifier-vs-human-grading prompt pairs (data only)

`positive.jsonl` and `negative.jsonl` are copied unchanged from
https://github.com/johny-b/public-steering-vectors at commit cb7158699ff5de220427b6f87756612f24a649ac,
`vectors/0007/` (MIT, © 2026 johny-b; LICENSE alongside). They are 270 tasks, each written twice, and the two copies
differ only in the grading sentence: an automated verifier on the positive side, a human rater on the negative side.
They are the prompts behind Betley, Treutlein & Dumas, "Steering towards automated grading degrades alignment".

Only these two data files are used. DD1 rebuilds the direction on Qwen3.8 from them; their Qwen3.6-27B vector and
their code are not used.
