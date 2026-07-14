# honeypot/

Cowrie's own config lives here once we move past the stock Docker image
defaults (Phase 1+): custom `cowrie.cfg` (fake hostname, fake filesystem
contents, banner text), and Phase 3 isolation config (network policy,
resource limits) referenced from `infra/docker-compose.yml`.

For the Phase 0 prototype we're running the stock `cowrie/cowrie` image
with no custom config — nothing to put here yet.
