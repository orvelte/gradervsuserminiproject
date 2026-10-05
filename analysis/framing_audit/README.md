# Framing audit (2026-10-05)

Read-only audit of the 274 prompt-only 2×2 and SF1 transcripts in Docent: was each arm built as specified, and does
the model's reasoning show it registered the framing cues?

```bash
.venv/bin/python analysis/framing_audit/fetch_docent.py /tmp/framing_runs.json     # list + get only; writes nothing to Docent
.venv/bin/python analysis/framing_audit/audit_construction.py /tmp/framing_runs.json
.venv/bin/python analysis/framing_audit/audit_cue_uptake.py /tmp/framing_runs.json
```

The cue counts are regex counts over assistant reasoning; samples were hand-read, but they are not a frozen rule.
