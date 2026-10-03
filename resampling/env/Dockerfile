# RS1 resampling image: the precommit_hook image with the agent loop replaced by resampling/rs_agent.py and the
# Harmony/Fireworks provider added. Everything else (task files, scorer, entrypoint, privilege model) is identical to
# environments/precommit_hook/Dockerfile, from which this file is derived (only the marked lines differ).
FROM python:3.11-slim
ENV PYTHONUNBUFFERED=1
WORKDIR /agent
RUN apt-get update && apt-get install -y --no-install-recommends git make gcc libc6-dev && rm -rf /var/lib/apt/lists/*
RUN git config --global user.email "container@modal" && git config --global user.name "Container"
RUN git config --global --add safe.directory '*'
RUN pip install "pytest>=7.0" pyyaml python-dotenv ruff "pydantic>=2.0" "mypy==1.20.2" "types-PyYAML==6.0.12.20260518" "types-requests==2.33.0.20260518"
COPY pyproject.toml /opt/pyproject.toml
COPY src /opt/src
RUN pip install -e /opt
# --- RS1: Harmony renderer + HTTP client (added) ---
RUN pip install "openai-harmony==0.0.8" "requests>=2.28"
# RS1: cache the Harmony tokenizer vocab in the image (containers run without network)
RUN mkdir -p /opt/tiktoken && python -c "import urllib.request, hashlib; p='/opt/tiktoken/o200k_base.tiktoken'; urllib.request.urlretrieve('https://openaipublic.blob.core.windows.net/encodings/o200k_base.tiktoken', p); assert hashlib.sha256(open(p,'rb').read()).hexdigest()=='446a9538cb6c348e3516120d7c08b09f57c36495e2acfffe59a5bf8b0cfb1a2d'"
ENV TIKTOKEN_ENCODINGS_BASE=/opt/tiktoken
RUN python -c "from openai_harmony import HarmonyEncodingName, load_harmony_encoding; load_harmony_encoding(HarmonyEncodingName.HARMONY_GPT_OSS); print('harmony vocab cached')"
COPY environments/precommit_hook/pyproject.toml /opt/task/pyproject.toml
COPY environments/precommit_hook/src_0   /opt/task/src_0
COPY environments/precommit_hook/src_258 /opt/task/src_258
COPY environments/precommit_hook/src_602 /opt/task/src_602
COPY environments/precommit_hook/generate_variants.py /opt/task/generate_variants.py
RUN cd /opt/task && python generate_variants.py
# --- RS1: the agent loop is replaced (added lines); states/run_step/tools/apply_patch/score/entrypoint are the originals ---
COPY resampling/rs_agent.py /opt/agent.py
COPY resampling/harmony.py /opt/harmony.py
COPY resampling/rs_provider.py /opt/rs_provider.py
COPY resampling/analysis/detector.py /opt/detector.py
COPY environments/precommit_hook/states.py /opt/states.py
COPY environments/precommit_hook/run_step.py /opt/run_step.py
COPY environments/precommit_hook/tools.py /opt/tools.py
COPY environments/precommit_hook/apply_patch.py /opt/apply_patch.py
RUN chmod +x /opt/apply_patch.py && install -m 755 /opt/apply_patch.py /usr/local/bin/apply_patch
COPY environments/precommit_hook/score.py /opt/score.py
COPY environments/precommit_hook/entrypoint.py /opt/entrypoint.py
RUN git init --separate-git-dir=/opt/.git && git add -A && git commit -m "pristine" --allow-empty && rm -f /agent/.git
RUN useradd -m -s /bin/bash dev && chown -R dev:dev /agent && chmod 700 /opt && chmod -R go-rwx /opt
CMD ["python", "/opt/entrypoint.py"]
