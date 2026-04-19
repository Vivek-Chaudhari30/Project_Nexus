#!/bin/sh
# Sandbox egress allowlist — runs once at container start.
# Requires NET_ADMIN capability (set in docker-compose).
# After setup, capability should be dropped via capsh.
set -e

# Default policy: drop all outbound except established/related
iptables -P OUTPUT DROP
iptables -A OUTPUT -m state --state ESTABLISHED,RELATED -j ACCEPT
# Allow loopback
iptables -A OUTPUT -o lo -j ACCEPT
# Allow DNS (needed to resolve allowlist domains)
iptables -A OUTPUT -p udp --dport 53 -j ACCEPT
iptables -A OUTPUT -p tcp --dport 53 -j ACCEPT

# Resolve and allow each domain in the allowlist
ALLOWLIST="/app/egress_allowlist.txt"
if [ -f "$ALLOWLIST" ]; then
    while IFS= read -r line; do
        # Skip comments and blank lines
        case "$line" in
            "#"*|"") continue ;;
        esac
        # Strip leading wildcard for resolution
        domain="${line#\*.}"
        ips=$(getent hosts "$domain" 2>/dev/null | awk '{print $1}') || true
        for ip in $ips; do
            iptables -A OUTPUT -d "$ip" -j ACCEPT
        done
    done < "$ALLOWLIST"
fi

echo "iptables egress rules applied"

# Hand off to the main process
exec "$@"
