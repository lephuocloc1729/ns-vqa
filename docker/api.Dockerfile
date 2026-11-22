# The backend API: FastAPI + the rules pipeline (Python) + SWI-Prolog (janus).
# Ubuntu 24.04 with the SWI-Prolog PPA, as in CI (SWI-Prolog >= 9.1 is required).
FROM ubuntu:24.04

ENV DEBIAN_FRONTEND=noninteractive PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 \
    PATH=/opt/venv/bin:$PATH
RUN apt-get update -q \
 && apt-get install -y -q --no-install-recommends software-properties-common gpg-agent ca-certificates curl \
 && add-apt-repository -y ppa:swi-prolog/stable \
 && apt-get update -q \
 && apt-get install -y -q --no-install-recommends swi-prolog-nox python3 python3-venv python3-dev build-essential \
 && rm -rf /var/lib/apt/lists/* \
 && python3 -m venv /opt/venv

WORKDIR /app
# dependencies first (a cached layer that changes only with pyproject.toml)
COPY pyproject.toml ./
RUN python - <<'PY' > /tmp/req.txt && pip install --no-cache-dir -r /tmp/req.txt
import tomllib
p = tomllib.load(open("pyproject.toml", "rb"))["project"]
print("\n".join(p["dependencies"] + p["optional-dependencies"]["api"]))
PY

# the code: the pipeline finds kb/ and prompts/ next to vqa/, so the tree is kept as in the repo
COPY vqa ./vqa
COPY app ./app
COPY kb ./kb
COPY prompts ./prompts
COPY web/e2e/fake_api.py ./web/e2e/fake_api.py
COPY docker/api-entrypoint.sh /usr/local/bin/api-entrypoint
RUN pip install --no-cache-dir --no-deps -e . \
 && swipl -q -g "consult('kb/load.pl'), halt" -t "halt(1)" \
 && useradd --create-home --uid 10001 vqa \
 && mkdir -p var/uploads cache/scenes logs \
 && chown -R vqa:vqa var cache logs \
 && chmod +x /usr/local/bin/api-entrypoint

USER vqa
EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=5s --start-period=30s --retries=5 \
  CMD curl -fsS http://127.0.0.1:8000/health || exit 1
ENTRYPOINT ["api-entrypoint"]
