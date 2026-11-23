#!/usr/bin/env bash
# Install SWI-Prolog >= 9.1 from its official PPA on Ubuntu: the CI runners and the API image.
#
#   sudo bash docker/install-swipl.sh            # needs software-properties-common (add-apt-repository)
#   sudo SWIPL_DEB_DIR=~/swipl-debs bash docker/install-swipl.sh
#
# SWIPL_DEB_DIR (optional; CI keeps it in its cache): after a good install the PPA's packages are
# saved there, and when the PPA cannot be reached they are installed from there instead.
#
# apt only warns when a repository is unreachable (e.g. Launchpad answering 503) and then installs
# Ubuntu's own older swi-prolog (9.0.x on 24.04), which the project cannot use and which breaks a
# janus_swi built against the PPA's version. So: retry until the PPA's package is the install
# candidate, and fail with a clear message if it never is, or if the installed version is too old.
set -euo pipefail
MIN=${SWIPL_MIN_VERSION:-90100}            # 9.1.0, as SWI-Prolog's version flag writes it
DELAY=${SWIPL_RETRY_DELAY:-15}             # seconds, times the attempt number

DEBS=${SWIPL_DEB_DIR:-}

from_saved() {   # install the PPA packages saved by an earlier good run, if there are any
  [ -n "$DEBS" ] && ls "$DEBS"/swi-prolog*.deb > /dev/null 2>&1 || return 1
  echo "install-swipl: installing the saved PPA packages from $DEBS" >&2
  apt-get update -q > /dev/null 2>&1 || true
  apt-get install -y -q --no-install-recommends "$DEBS"/swi-prolog*.deb > /dev/null
}

check_version() {
  local version
  version=$(swipl -g "current_prolog_flag(version, V), write(V), nl" -t halt)
  if [ "$version" -lt "$MIN" ]; then
    echo "install-swipl: SWI-Prolog $version is older than $MIN" >&2
    exit 1
  fi
  swipl --version
}

added=""
for attempt in 1 2 3; do                   # adding the PPA also asks Launchpad for its key
  if add-apt-repository -y ppa:swi-prolog/stable > /dev/null 2>&1; then added=1; break; fi
  echo "install-swipl: adding the PPA failed, retry $attempt of 3" >&2
  sleep $((attempt * DELAY))
done
ok=""
if [ -n "$added" ]; then
  for attempt in 1 2 3 4 5; do
    apt-get update -q > /dev/null 2>&1 || true
    candidate=$(apt-cache policy swi-prolog-nox | awk '/Candidate:/ {print $2}')
    case "$candidate" in
      *ppa*)
        if apt-get install -y -q --no-install-recommends swi-prolog-nox > /dev/null 2>&1; then ok=1; break; fi
        echo "install-swipl: downloading the PPA's packages failed, retry $attempt of 5" >&2 ;;
      *) echo "install-swipl: the PPA is not reachable yet (candidate '$candidate'), retry $attempt of 5" >&2 ;;
    esac
    sleep $((attempt * DELAY))
  done
fi
if [ -n "$ok" ]; then
  if [ -n "$DEBS" ]; then                  # keep this good install's packages for an outage
    mkdir -p "$DEBS" && rm -f "$DEBS"/swi-prolog*.deb
    (cd "$DEBS" && apt-get download swi-prolog-nox swi-prolog-core swi-prolog-core-packages > /dev/null 2>&1) || true
  fi
elif ! from_saved; then
  echo "install-swipl: the SWI-Prolog PPA could not be reached and no saved packages exist;" \
       "refusing Ubuntu's older swi-prolog" >&2
  exit 1
fi
check_version
