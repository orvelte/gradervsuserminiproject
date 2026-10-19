# History

Records from the experiments that led to the deployment simulation. Their code was removed from the working branch;
it is at tag `deploysim-v1-results` on `main`.

| file | what it is |
|---|---|
| `README_2x2.md` | the original README: the prompt-only 2×2 (graded vs user wrapper, with and without stated oversight) and its condition table |
| `BUILD_TASK_2x2.md`, `BUILD_REPORT_2x2.md` | the build specification and report for that 2×2 |
| `PROBE_FINDINGS.md` | why the project moved from DeepSeek v4 Pro to GPT-OSS-120B |
| `figures/` | figures from the 2×2, the structural-framing versions, the resampling experiment and the follow-up pilots |

Summary of what was found: prompt framing, stated oversight and two structural-framing versions left gaming at about
half of runs, and none removed the model's inference that the task was a test. The deployment simulation was built to
change the shape of the episode rather than its labels.
