#!/usr/bin/env bash
set -euo pipefail

# Blocks new outbound connections from the Cowrie container while preserving
# inbound DNAT/published-port traffic and its established replies.
#
# Run on the Linux VPS after:
#   docker compose --env-file infra/.env.prod -f infra/docker-compose.prod.yml up -d
#
# Requires root and iptables. Re-run after recreating the Cowrie container,
# because Docker may assign a new container IP.

COWRIE_CONTAINER="${COWRIE_CONTAINER:-honeypot-cowrie}"
CHAIN="${CHAIN:-HONEYPOT_EGRESS}"

if [[ "${EUID}" -ne 0 ]]; then
  echo "Run as root: sudo $0" >&2
  exit 1
fi

if ! command -v docker >/dev/null 2>&1; then
  echo "docker is required" >&2
  exit 1
fi

if ! command -v iptables >/dev/null 2>&1; then
  echo "iptables is required" >&2
  exit 1
fi

COWRIE_IP="$(
  docker inspect -f '{{range .NetworkSettings.Networks}}{{if eq .NetworkID ""}}{{else}}{{.IPAddress}}{{end}}{{end}}' "${COWRIE_CONTAINER}"
)"

if [[ -z "${COWRIE_IP}" ]]; then
  echo "Could not determine ${COWRIE_CONTAINER} container IP" >&2
  exit 1
fi

iptables -N "${CHAIN}" 2>/dev/null || true
iptables -F "${CHAIN}"

iptables -C DOCKER-USER -j "${CHAIN}" 2>/dev/null || iptables -I DOCKER-USER 1 -j "${CHAIN}"

iptables -A "${CHAIN}" -m conntrack --ctstate ESTABLISHED,RELATED -j RETURN
iptables -A "${CHAIN}" -s "${COWRIE_IP}" -j LOG --log-prefix "honeypot-egress-block " --log-level 4
iptables -A "${CHAIN}" -s "${COWRIE_IP}" -j DROP
iptables -A "${CHAIN}" -j RETURN

echo "Blocked new outbound traffic from ${COWRIE_CONTAINER} (${COWRIE_IP})."
echo "Verify with: sudo iptables -S ${CHAIN}"
