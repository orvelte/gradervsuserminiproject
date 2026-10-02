FROM python:3.11-slim
# precommit_hook_sf: the structural-framing copy of environments/precommit_hook (SF1). Image contents
# are identical except agent.py/run_step.py/states.py/entrypoint.py and the added sf_framing.py.

# =============================================================================
# RUNTIME ENVIRONMENT
# =============================================================================
ENV PYTHONUNBUFFERED=1
WORKDIR /agent

# =============================================================================
# SYSTEM DEPENDENCIES
# =============================================================================
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    make \
    gcc \
    libc6-dev \
    && rm -rf /var/lib/apt/lists/*

RUN git config --global user.email "container@modal" && \
    git config --global user.name "Container"
# Root (the harness) runs git against a workspace owned by `dev`, which git
# otherwise refuses as "dubious ownership".
RUN git config --global --add safe.directory '*'

# =============================================================================
# PYTHON DEPENDENCIES
# =============================================================================
RUN pip install \
    "pytest>=7.0" \
    pyyaml \
    python-dotenv \
    ruff \
    "pydantic>=2.0" \
    "mypy==1.20.2" \
    "types-PyYAML==6.0.12.20260518" \
    "types-requests==2.33.0.20260518"

# =============================================================================
# INSTALL SHARED PACKAGE
# =============================================================================
COPY pyproject.toml /opt/pyproject.toml
COPY src /opt/src
RUN pip install -e /opt

# =============================================================================
# COPY TASK FILES
# =============================================================================
# (Ordered before the harness files so that editing agent.py/score.py reuses the
# cached generate_variants layer. Image contents are identical to upstream.)
COPY structural_framing/env/precommit_hook_sf/pyproject.toml /opt/task/pyproject.toml
COPY structural_framing/env/precommit_hook_sf/src_0   /opt/task/src_0
COPY structural_framing/env/precommit_hook_sf/src_258 /opt/task/src_258
COPY structural_framing/env/precommit_hook_sf/src_602 /opt/task/src_602
COPY structural_framing/env/precommit_hook_sf/generate_variants.py /opt/task/generate_variants.py
RUN cd /opt/task && python generate_variants.py

# =============================================================================
# COPY ENVIRONMENT FILES
# =============================================================================
COPY structural_framing/env/precommit_hook_sf/agent.py /opt/agent.py
COPY structural_framing/env/precommit_hook_sf/states.py /opt/states.py
COPY structural_framing/env/precommit_hook_sf/run_step.py /opt/run_step.py
COPY structural_framing/env/precommit_hook_sf/tools.py /opt/tools.py
COPY structural_framing/env/precommit_hook_sf/apply_patch.py /opt/apply_patch.py
# Expose apply_patch as a CLI (reads patch from stdin) for the agent's shell.
# Installed as a copy, not a symlink into
# /opt: /opt is locked to root below, and the CLI must stay runnable from the
# agent's `dev` shell. The module is self-contained (stdlib only).
RUN chmod +x /opt/apply_patch.py && install -m 755 /opt/apply_patch.py /usr/local/bin/apply_patch
COPY structural_framing/env/precommit_hook_sf/score.py /opt/score.py
COPY structural_framing/env/precommit_hook_sf/entrypoint.py /opt/entrypoint.py
COPY structural_framing/env/precommit_hook_sf/sf_framing.py /opt/sf_framing.py

# =============================================================================
# PRISTINE SNAPSHOT (for container reuse reset in run_modal.py)
# =============================================================================
RUN git init --separate-git-dir=/opt/.git && git add -A && git commit -m "pristine" --allow-empty && rm -f /agent/.git

# =============================================================================
# PRIVILEGE SEPARATION
# =============================================================================
# The agent loop runs as root (reads /opt, holds the API key); the agent's shell
# commands are dropped to `dev` per-command via the shared hardened run_command,
# with a sanitized environment. Lock /opt so the harness, the config bind mount,
# the grader (score.py) and every src_* dose variant are invisible to the agent.
# The entrypoint copies the selected variant into /agent and hands the workspace
# (plus the .git it initializes there) to `dev` at runtime.
RUN useradd -m -s /bin/bash dev \
    && chown -R dev:dev /agent \
    && chmod 700 /opt && chmod -R go-rwx /opt

# =============================================================================
# RUNTIME CONFIGURATION
# =============================================================================
CMD ["python", "/opt/entrypoint.py"]
