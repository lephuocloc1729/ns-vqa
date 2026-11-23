#!/usr/bin/env bash
# Install SWI-Prolog >= 9.1 from its official PPA on Ubuntu: the CI runners and the API image.
#
#   sudo bash docker/install-swipl.sh            # needs software-properties-common (add-apt-repository)
#   sudo SWIPL_DEB_DIR=~/swipl-debs bash docker/install-swipl.sh
#
# When the PPA cannot be reached, in this order:
# 1. SWIPL_DEB_DIR (optional; CI keeps it in its cache): after a good install, the packages that
#    came from the PPA are saved there, and installed from there now. Only PPA packages are saved
#    or installed: the PPA ships SWI-Prolog as one package (swi-prolog-nox), and Ubuntu's own
#    swi-prolog-core 9.0.x next to it gave a 9.0 install (CI, 2026-11-23).
# 2. The pinned PPA package from Launchpad's file server (launchpadlibrarian.net, a different host
#    from the PPA archive, which is what goes down), checked against its sha256 (SWIPL_PINNED_*).
#
# apt only warns when a repository is unreachable (e.g. Launchpad answering 503) and then installs
# Ubuntu's own older swi-prolog (9.0.x on 24.04), which the project cannot use and which breaks a
# janus_swi built against the PPA's version. So: retry until the PPA's package is the install
# candidate, and fail with a clear message if it never is, or if the installed version is too old.
set -euo pipefail
MIN=${SWIPL_MIN_VERSION:-90100}            # 9.1.0, as SWI-Prolog's version flag writes it
DELAY=${SWIPL_RETRY_DELAY:-15}             # seconds, times the attempt number

DEBS=${SWIPL_DEB_DIR:-}
# the version the API's base image runs (docker/base.Dockerfile); amd64, the CI runners' and server's
PINNED_URL=${SWIPL_PINNED_URL:-https://launchpadlibrarian.net/885379013/swi-prolog-nox_11.0.0-1-g551e3f831-nobleppa2_amd64.deb}
PINNED_SHA256=${SWIPL_PINNED_SHA256:-d02edef7a084fc8eef4375bf541097bc65a9f858f710ea03921ea5ce9dd4656d}

from_saved() {   # install the PPA packages saved by an earlier good run, if there are any
  [ -n "$DEBS" ] && ls "$DEBS"/swi-prolog*ppa*.deb > /dev/null 2>&1 || return 1
  echo "install-swipl: installing the saved PPA packages from $DEBS" >&2
  apt-get update -q > /dev/null 2>&1 || true
  apt-get install -y -q --no-install-recommends "$DEBS"/swi-prolog*ppa*.deb > /dev/null
}

from_pinned() {  # the pinned PPA package from Launchpad's file server, checked against its sha256
  [ "$(dpkg --print-architecture)" = amd64 ] || return 1
  local tmp
  tmp=$(mktemp -d)
  echo "install-swipl: downloading the pinned PPA package from Launchpad's file server" >&2
  for attempt in 1 2 3; do
    if curl -fsSL --max-time 120 -o "$tmp/swi-prolog-nox.deb" "$PINNED_URL"; then break; fi
    rm -f "$tmp/swi-prolog-nox.deb"
    sleep $((attempt * DELAY))
  done
  [ -f "$tmp/swi-prolog-nox.deb" ] || return 1
  if ! echo "$PINNED_SHA256  $tmp/swi-prolog-nox.deb" | sha256sum -c - > /dev/null 2>&1; then
    echo "install-swipl: the pinned package's sha256 does not match; not installing it" >&2
    return 1
  fi
  apt-get update -q > /dev/null 2>&1 || true
  apt-get install -y -q --no-install-recommends "$tmp/swi-prolog-nox.deb" > /dev/null
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
  if [ -n "$DEBS" ]; then                  # keep the packages this install took from the PPA
    mkdir -p "$DEBS" && rm -f "$DEBS"/*.deb
    pkgs=$(dpkg-query -W -f '${Package}=${Version}\n' 'swi-prolog*' 2>/dev/null | grep ppa || true)
    # shellcheck disable=SC2086
    [ -z "$pkgs" ] || (cd "$DEBS" && apt-get download $pkgs > /dev/null 2>&1) || true
  fi
elif ! from_saved && ! from_pinned; then
  echo "install-swipl: the SWI-Prolog PPA could not be reached, and neither saved packages nor" \
       "the pinned package could be installed; refusing Ubuntu's older swi-prolog" >&2
  exit 1
fi
check_version
