#!/usr/bin/env bash
# swap-kolla-image.sh - repoint puppet-generated docker-run-*-start.sh at another registry/tag
set -euo pipefail

BAK_SUFFIX=".preswap"
DRY=0

usage() {
  cat <<EOF
Usage:
  $0 swap --registry <reg/ns> [--tag <tag>] [--dry-run] <service> [service...]
  $0 rollback <service> [service...]
  $0 status   <service> [service...]

Image name is preserved per service, only registry/namespace and tag change.

Example:
  $0 swap --registry registry.rc.nectar.org.au/temp --tag 2024.1-local \\
      nova-api nova-api-metadata nova-conductor nova-scheduler
EOF
  exit 1
}

script_for() { echo "/usr/local/bin/docker-run-$1-start.sh"; }
unit_for()   { echo "docker-$1.service"; }

IMAGE_RE='[A-Za-z0-9._-]+(:[0-9]+)?/[A-Za-z0-9._/-]+:[A-Za-z0-9._-]+'

current_image() {
  grep -oE "$IMAGE_RE" "$1" | tail -1
}

puppet_off() {
  command -v puppet >/dev/null || return 0
  (( DRY )) && { echo "[dry-run] would disable puppet agent"; return 0; }
  puppet agent --disable "kolla image swap $(date -Is)" || true
  echo "puppet agent disabled"
}

do_swap() {
  local reg="" tag="" svcs=()
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --registry) reg=${2:?}; shift 2 ;;
      --tag)      tag=${2:?}; shift 2 ;;
      --dry-run)  DRY=1; shift ;;
      -*)         usage ;;
      *)          svcs+=("$1"); shift ;;
    esac
  done
  [[ -n $reg && ${#svcs[@]} -gt 0 ]] || usage
  reg=${reg%/}

  # resolve target image per service first, pull all, then touch nothing until every pull succeeds
  declare -A NEW
  for svc in "${svcs[@]}"; do
    local f cur name oldtag
    f=$(script_for "$svc")
    [[ -f $f ]] || { echo "missing $f"; exit 1; }
    cur=$(current_image "$f")
    [[ -n $cur ]] || { echo "no image found in $f"; exit 1; }
    name=${cur##*/}; name=${name%%:*}
    oldtag=${cur##*:}
    NEW[$svc]="${reg}/${name}:${tag:-$oldtag}"
    echo "== $svc: $cur -> ${NEW[$svc]}"
  done

  for svc in "${svcs[@]}"; do
    if (( DRY )); then
      echo "[dry-run] would pull ${NEW[$svc]}"
    else
      docker image inspect "${NEW[$svc]}" >/dev/null 2>&1 || docker pull "${NEW[$svc]}"
    fi
  done
  (( DRY )) && exit 0

  puppet_off

  for svc in "${svcs[@]}"; do
    local f cur img
    f=$(script_for "$svc"); cur=$(current_image "$f"); img=${NEW[$svc]}
    [[ -f ${f}${BAK_SUFFIX} ]] || cp -a "$f" "${f}${BAK_SUFFIX}"
    sed -i -E "s#(^|[[:space:]])${cur//./\\.}([[:space:]]|\$)#\1${img}\2#" "$f"
    grep -qF "$img" "$f" || { echo "sed failed on $f"; exit 1; }
    systemctl restart "$(unit_for "$svc")"
  done
  sleep 5
  do_status "${svcs[@]}"
}

do_rollback() {
  puppet_off
  for svc in "$@"; do
    local f; f=$(script_for "$svc")
    [[ -f ${f}${BAK_SUFFIX} ]] || { echo "no backup for $svc"; continue; }
    mv "${f}${BAK_SUFFIX}" "$f"
    systemctl restart "$(unit_for "$svc")"
    echo "== $svc rolled back"
  done
  sleep 5
  do_status "$@"
}

do_status() {
  for svc in "$@"; do
    printf '%-24s %-12s %s\n' "$svc" \
      "$(systemctl is-active "$(unit_for "$svc")")" \
      "$(docker inspect -f '{{.Config.Image}}' "$svc" 2>/dev/null || echo 'not running')"
  done
}

[[ $# -ge 1 ]] || usage
cmd=$1; shift
case "$cmd" in
  swap)     do_swap "$@" ;;
  rollback) [[ $# -ge 1 ]] || usage; do_rollback "$@" ;;
  status)   [[ $# -ge 1 ]] || usage; do_status "$@" ;;
  *) usage ;;
esac
