"""READ-ONLY pull of the 2x2 and SF1 transcripts from Docent (list + get only; nothing is written to Docent)."""
import json, os, sys, collections
from concurrent.futures import ThreadPoolExecutor
from dotenv import load_dotenv
load_dotenv(".env")
from docent import Docent
client = Docent(api_key=os.environ["DOCENT_API_KEY"]); cid = os.environ["DOCENT_COLLECTION_ID"]
ids = list(client.list_agent_run_ids(cid)); print("runs in collection:", len(ids), flush=True)

def text_of(c):
    if isinstance(c, str): return c
    return "".join(getattr(b, "text", "") or "" for b in c if getattr(b, "type", "") != "reasoning")

def one(rid):
    for attempt in range(3):
        try:
            ar = client.get_agent_run(cid, rid); break
        except Exception as e:
            err = e
    else:
        return {"id": rid, "error": repr(err)[:200]}
    md = ar.metadata or {}
    keep = md.get("condition_id") in ("N0", "G0", "G1", "U0", "U1") or str(md.get("condition_id", "")).startswith("SF1") or md.get("experiment") == "structural_framing_v1"
    rec = {"id": rid, "name": ar.name, "metadata": md, "kept": keep}
    if keep:
        msgs = []
        for m in ar.transcripts[0].messages:
            d = {"role": m.role, "text": text_of(m.content)}
            if m.role == "assistant":
                d["reasoning"] = "\n".join(b.reasoning for b in m.content if getattr(b, "type", "") == "reasoning") if isinstance(m.content, list) else ""
                d["tool_calls"] = [{"name": tc.function, "arguments": tc.arguments} for tc in (m.tool_calls or [])]
            msgs.append(d)
        rec["messages"] = msgs
    return rec

with ThreadPoolExecutor(8) as ex:
    recs = list(ex.map(one, ids))
print(collections.Counter((r["metadata"].get("experiment"), r["metadata"].get("condition_id"), bool(r["metadata"].get("superseded"))) if "metadata" in r else "ERROR" for r in recs))
json.dump([r for r in recs if r.get("kept")], open(sys.argv[1], "w"))
print("saved", sum(bool(r.get("kept")) for r in recs), "errors", sum("error" in r for r in recs))
