#!/usr/bin/env bash
set -euo pipefail

# Blocks new outbound connections from the Cowrie container while preserving
# inbound DNAT/published-port traffic and its established replies.
#
# Run on the Linux VPS after:
#   docker compose --env-file infra/.env.prod -f infra/docker-compose.prod.yml up -d
#
# Requires root and iptables. The prod compose file pins Cowrie to
# 172.19.0.2 and infra/honeypot-egress.service runs this at every boot with
# COWRIE_IP set, so the rule no longer depends on the container being up.
# Without COWRIE_IP, the IP is read from the running container.

COWRIE_CONTAINER="${COWRIE_CONTAINER:-honeypot-cowrie}"
CHAIN="${CHAIN:-HONEYPOT_EGRESS}"

if [[ "${EUID}" -ne 0 ]]; then
  echo "Run as root: sudo $0" >&2
  exit 1
fi

if ! command -v iptables >/dev/null 2>&1; then
  echo "iptables is required" >&2
  exit 1
fi

COWRIE_IP="${COWRIE_IP:-$(
  docker inspect -f '{{range .NetworkSettings.Networks}}{{if eq .NetworkID ""}}{{else}}{{.IPAddress}}{{end}}{{end}}' "${COWRIE_CONTAINER}"
)}"

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
