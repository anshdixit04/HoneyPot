# Phase 4 VPS Deployment Runbook

This is the first phase where Cowrie can be exposed to the public internet.
Do not run this from a home network. Use a single-purpose VPS with no personal
files, no reused credentials, and no other projects on it.

## 1. VPS Baseline

Use a small Ubuntu/Debian VPS. Before starting the honeypot:

1. Create a non-root sudo user.
2. Use SSH keys only; disable password SSH login.
3. Keep your real admin SSH separate from the honeypot port. Do not map Cowrie
   to public port 22 until admin access has moved to another port or VPN.
4. Install Docker Engine and the Docker Compose plugin.
5. Turn on the host firewall and allow only admin SSH, dashboard HTTP/HTTPS,
   and the chosen Cowrie ports.

Example UFW policy:

```bash
sudo ufw default deny incoming
sudo ufw default allow outgoing
sudo ufw allow OpenSSH
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw allow 2222/tcp
sudo ufw allow 2223/tcp
sudo ufw enable
```

## 2. Configure Production Env

Copy the example file on the VPS:

```bash
cp infra/.env.prod.example infra/.env.prod
```

Start with non-privileged honeypot ports:

```dotenv
HONEYPOT_SSH_PORT=2222
HONEYPOT_TELNET_PORT=2223
DASHBOARD_HTTP_PORT=80
```

Later, if you want Cowrie on the real SSH/Telnet defaults, move admin SSH
first, then set:

```dotenv
HONEYPOT_SSH_PORT=22
HONEYPOT_TELNET_PORT=23
```

## 3. Start The Stack

```bash
docker compose --env-file infra/.env.prod -f infra/docker-compose.prod.yml up -d --build
docker compose --env-file infra/.env.prod -f infra/docker-compose.prod.yml ps
```

Production containers:

- `honeypot-cowrie`: public SSH/Telnet honeypot, hardened with read-only root,
  dropped capabilities, no-new-privileges, and resource limits.
- `honeypot-backend`: private FastAPI service. It has no published port.
- `honeypot-dashboard`: public dashboard HTTP server and reverse proxy.

The dashboard proxies `/api`, `/healthz`, and `/ws` to the private backend, so
the browser does not need hardcoded `localhost` URLs.

## 4. Apply Cowrie Egress Block

After the stack is running, block new outbound connections from Cowrie:

```bash
sudo bash infra/iptables-honeypot-egress.sh
sudo iptables -S HONEYPOT_EGRESS
```

Why this is separate from Compose: Docker's published ports use kernel DNAT,
which preserves the attacker's source IP for GeoIP. A plain TCP relay would
hide the real source IP. The `DOCKER-USER` iptables chain lets us preserve DNAT
for inbound traffic while dropping new outbound traffic from Cowrie.

Re-run the script after recreating the Cowrie container because Docker may
assign a new container IP.

To persist rules across reboot on Ubuntu/Debian:

```bash
sudo apt-get install iptables-persistent
sudo netfilter-persistent save
```

## 5. Smoke Test

From the VPS:

```bash
curl http://127.0.0.1/healthz
docker logs --tail=50 honeypot-backend
```

From your laptop:

```bash
ssh -p 2222 root@<vps-ip>
```

Try fake credentials. The attempt should appear in the dashboard and backend
logs. If the public IP does not show on the dashboard, stop and investigate
before sharing the link.

## 6. HTTPS And Domain

For a resume link, put HTTPS in front of the dashboard. The simplest path is a
host-level reverse proxy such as Caddy or Nginx listening on 443 and forwarding
to `http://127.0.0.1:80`, or a tunnel/CDN that supports WebSockets.

The frontend uses relative `/api` and `/ws` URLs, so it will automatically use
`wss://` when loaded over HTTPS.

## 7. Public Exposure Checklist

Do not share the public link until all of these are true:

- Admin SSH is key-only and separate from Cowrie.
- Host firewall allows only the intended ports.
- `docker compose ... ps` shows all services running.
- `sudo iptables -S HONEYPOT_EGRESS` shows a DROP rule for the Cowrie IP.
- The dashboard loads from the public URL.
- A fake login attempt appears with the real source IP, not a proxy/container IP.
- Backend port `8000` is not publicly reachable.
- The VPS has no unrelated secrets, projects, or personal data.
