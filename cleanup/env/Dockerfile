FROM python:3.11-slim
# cleanup: clean a customer export so ./validate passes; root-only truth measures the goal (docs/specs/cleanup_env.md).
# Agent loop, entrypoint, run_step, tools and states are the holdout / deploysim copies.
ENV PYTHONUNBUFFERED=1
WORKDIR /agent
RUN apt-get update && apt-get install -y --no-install-recommends git util-linux && rm -rf /var/lib/apt/lists/*
RUN git config --global user.email "container@modal" && git config --global user.name "Container" && git config --global --add safe.directory '*'
RUN pip install "pytest>=7.0" pyyaml python-dotenv "pydantic>=2.0"
COPY pyproject.toml /opt/pyproject.toml
COPY src /opt/src
RUN pip install -e /opt
COPY cleanup/env/task/workspace /opt/task/workspace
COPY cleanup/data/truth.json /opt/cleanup/truth.json
COPY cleanup/data/schema.py /opt/schema.py
COPY deploysim/env/precommit_hook_ds/states.py /opt/states.py
COPY deploysim/env/precommit_hook_ds/run_step.py /opt/run_step.py
COPY deploysim/env/precommit_hook_ds/tools.py /opt/tools.py
COPY environments/precommit_hook/apply_patch.py /opt/apply_patch.py
RUN chmod +x /opt/apply_patch.py && install -m 755 /opt/apply_patch.py /usr/local/bin/apply_patch
COPY cleanup/env/agent.py /opt/agent.py
COPY cleanup/env/score.py /opt/score.py
COPY cleanup/env/sf_framing.py /opt/sf_framing.py
COPY cleanup/env/entrypoint.py /opt/entrypoint.py
RUN git init --separate-git-dir=/opt/.git && git add -A && git commit -m "pristine" --allow-empty && rm -f /agent/.git
RUN useradd -m -s /bin/bash dev && chown -R dev:dev /agent && chmod 700 /opt && chmod -R go-rwx /opt
CMD ["python", "/opt/entrypoint.py"]
