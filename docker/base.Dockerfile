# The base of the API image: Ubuntu 24.04, Python 3 and SWI-Prolog (>= 9.1) from its PPA.
#
# Built once by .github/workflows/base-image.yml and kept in GHCR, so building the API image never
# needs Launchpad (the PPA's host; its outages broke CI on 2026-11-23). It also pins the SWI-Prolog
# version: the API image changes Prolog only when this base is rebuilt and its new tag is chosen.
FROM ubuntu:24.04
LABEL org.opencontainers.image.source=https://github.com/lephuocloc1729/ns-vqa \
      org.opencontainers.image.description="SignCite API base: Ubuntu 24.04, Python 3, SWI-Prolog from its PPA"

ENV DEBIAN_FRONTEND=noninteractive PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 \
    PATH=/opt/venv/bin:$PATH
COPY docker/install-swipl.sh /tmp/install-swipl.sh
RUN apt-get update -q \
 && apt-get install -y -q --no-install-recommends software-properties-common gpg-agent ca-certificates curl \
    python3 python3-venv python3-dev build-essential \
 && bash /tmp/install-swipl.sh \
 && rm -rf /var/lib/apt/lists/* /tmp/install-swipl.sh \
 && python3 -m venv /opt/venv
