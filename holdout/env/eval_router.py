"""Run inside a throwaway copy of the workspace, as `dev`: read unlabelled tickets (JSON on stdin), print the
router's predictions (JSON on stdout). The labels never enter this process."""
import contextlib
import io
import json
import sys

sys.path.insert(0, ".")
tickets = json.load(sys.stdin)
out = []
with contextlib.redirect_stdout(io.StringIO()):
    try:
        import router
        route = router.route
    except Exception as exc:
        route = None; err = f"import error: {type(exc).__name__}"
    for t in tickets:
        if route is None:
            out.append(err); continue
        try:
            out.append(str(route(dict(t))))
        except Exception as exc:
            out.append(f"error: {type(exc).__name__}")
sys.stdout.write(json.dumps(out))
