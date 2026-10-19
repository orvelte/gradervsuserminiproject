FROM python:3.11-slim
# holdout: ticket routing scored on a visible labelled sample; a root-only held-out set measures the goal
# (docs/specs/holdout_env.md). Agent loop, run_step, tools and states are deploysim's precommit_hook_ds copies.
ENV PYTHONUNBUFFERED=1
WORKDIR /agent

RUN apt-get update && apt-get install -y --no-install-recommends git util-linux && rm -rf /var/lib/apt/lists/*
RUN git config --global user.email "container@modal" && git config --global user.name "Container" && git config --global --add safe.directory '*'
RUN pip install "pytest>=7.0" pyyaml python-dotenv "pydantic>=2.0"

COPY pyproject.toml /opt/pyproject.toml
COPY src /opt/src
RUN pip install -e /opt

# Task files: the pristine workspace (stub, sample, ./score) and the held-out set (root-only, never in /agent).
COPY holdout/env/task/workspace /opt/task/workspace
COPY holdout/data/holdout.csv /opt/holdout/holdout.csv

COPY deploysim/env/precommit_hook_ds/states.py /opt/states.py
COPY deploysim/env/precommit_hook_ds/run_step.py /opt/run_step.py
COPY deploysim/env/precommit_hook_ds/tools.py /opt/tools.py
COPY environments/precommit_hook/apply_patch.py /opt/apply_patch.py
RUN chmod +x /opt/apply_patch.py && install -m 755 /opt/apply_patch.py /usr/local/bin/apply_patch
COPY holdout/env/agent.py /opt/agent.py
COPY holdout/env/score.py /opt/score.py
COPY holdout/env/eval_router.py /opt/eval_router.py
COPY holdout/env/sf_framing.py /opt/sf_framing.py
COPY holdout/env/entrypoint.py /opt/entrypoint.py

RUN git init --separate-git-dir=/opt/.git && git add -A && git commit -m "pristine" --allow-empty && rm -f /agent/.git

# Agent shell runs as `dev`; /opt (harness, scorer, held-out set, pristine files) is root-only.
RUN useradd -m -s /bin/bash dev && chown -R dev:dev /agent && chmod 700 /opt && chmod -R go-rwx /opt
CMD ["python", "/opt/entrypoint.py"]
