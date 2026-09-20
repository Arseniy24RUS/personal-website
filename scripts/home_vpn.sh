#!/usr/bin/env bash
# Ephemeral Actions runner only. Never print the configuration, addresses or log.
set -euo pipefail
private="${RUNNER_TEMP:?}/portfolio-private"
collector="portfolio"
interface="tun0"
script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"

check_route() {
  test -s "$private/openvpn.pid" && sudo kill -0 "$(cat "$private/openvpn.pid")"
  ip link show "$interface" >/dev/null
  grep -q 'Initialization Sequence Completed' "$private/openvpn.log"
  local current
  current="$(curl -4fsS --interface "$interface" --max-time 25 https://api.ipify.org)"
  test -n "$current" && test "$current" = "$(cat "$private/expected-ip")"
  # Validate representative routes, including the SSO provider.
  for host in www.elibrary.ru www.webofscience.com access.clarivate.com orcid.org api.elsevier.com; do
    local address
    address="$(getent ahostsv4 "$host" | awk 'NR==1{print $1}')"
    test -n "$address"
    ip -4 route get "$address" | grep -q 'dev tun0'
  done
  echo 'Home tunnel and provider routes verified.'
}

case "${1:-}" in
  start)
    test -n "${ELIBRARY_OPENVPN_CONFIG_B64:-}" || { echo 'Home VPN secret is missing.'; exit 1; }
    umask 077
    mkdir -p "$private"
    chmod 700 "$private"
    printf '%s' "$ELIBRARY_OPENVPN_CONFIG_B64" | base64 --decode > "$private/home.ovpn"
    before="$(curl -4fsS --max-time 20 https://api.ipify.org)"
    # Only the dedicated collector account is restricted. The Actions control
    # plane and the OpenVPN transport keep their normal access.
    id "$collector" >/dev/null 2>&1 || sudo useradd --create-home --shell /bin/bash "$collector"
    sudo iptables -N PORTFOLIO_VPN
    sudo iptables -A PORTFOLIO_VPN -o lo -j ACCEPT
    sudo iptables -A PORTFOLIO_VPN -o "$interface" -j ACCEPT
    sudo iptables -A PORTFOLIO_VPN -j REJECT
    sudo iptables -I OUTPUT 1 -m owner --uid-owner "$collector" -j PORTFOLIO_VPN
    sudo ip6tables -I OUTPUT 1 -m owner --uid-owner "$collector" -j REJECT
    # Runtime resolver settings are confined to this disposable runner.
    sudo openvpn --config "$private/home.ovpn" --dev "$interface" \
      --redirect-gateway def1 --data-ciphers-fallback AES-128-CBC \
      --allow-compression yes --script-security 2 \
      --up "$script_dir/home_vpn_dns.sh" --down "$script_dir/home_vpn_dns.sh" \
      --daemon --writepid "$private/openvpn.pid" --log "$private/openvpn.log"
    ready=false
    for attempt in $(seq 1 60); do
      if sudo grep -q 'Initialization Sequence Completed' "$private/openvpn.log"; then ready=true; break; fi
      sleep 2
    done
    test "$ready" = true || { echo 'Home VPN initialization failed; direct collection is disabled.'; exit 1; }
    sudo chown "$(id -u):$(id -g)" "$private/openvpn.log" "$private/openvpn.pid"
    after="$(curl -4fsS --interface "$interface" --max-time 25 https://api.ipify.org)"
    test -n "$after" && test "$before" != "$after" || { echo 'Home VPN egress could not be verified.'; exit 1; }
    printf '%s' "$after" > "$private/expected-ip"
    sudo chgrp "$collector" "$private" "$private/expected-ip"
    chmod 750 "$private"
    chmod 640 "$private/expected-ip"
    # Prevent the system resolver (running as another uid) leaking collector
    # DNS through an uplink if it tries an alternative server after tunnel loss.
    sudo iptables -N PORTFOLIO_DNS
    sudo iptables -A PORTFOLIO_DNS -o lo -j RETURN
    sudo iptables -A PORTFOLIO_DNS -o "$interface" -j RETURN
    sudo iptables -A PORTFOLIO_DNS -j REJECT
    sudo iptables -I OUTPUT 1 -p udp --dport 53 -j PORTFOLIO_DNS
    sudo iptables -I OUTPUT 1 -p tcp --dport 53 -j PORTFOLIO_DNS
    sudo ip6tables -I OUTPUT 1 -p udp --dport 53 ! -o lo -j REJECT
    sudo ip6tables -I OUTPUT 1 -p tcp --dport 53 ! -o lo -j REJECT
    check_route
    ;;
  check) check_route ;;
  test-isolation)
    # Simulate the collector losing its permitted tunnel while the Actions
    # control plane stays reachable. Both tunnel and direct routes must fail.
    sudo iptables -I PORTFOLIO_VPN 1 -o "$interface" -j REJECT
    trap 'sudo iptables -D PORTFOLIO_VPN -o "$interface" -j REJECT' EXIT
    endpoint="$(getent ahostsv4 api.ipify.org | awk 'NR==1{print $1}')"
    uplink="$(ip -4 route show default | awk 'NR==1{for(i=1;i<=NF;i++)if($i=="dev"){print $(i+1);exit}}')"
    test -n "$endpoint" && test -n "$uplink"
    for device in "$interface" "$uplink"; do
      if sudo -u "$collector" curl -4fsS --interface "$device" --max-time 8 \
        --resolve "api.ipify.org:443:$endpoint" https://api.ipify.org >/dev/null 2>&1; then
        echo 'Collector isolation failed; collection is disabled.'; exit 1
      fi
    done
    sudo ip6tables -C OUTPUT -m owner --uid-owner "$collector" -j REJECT
    echo 'Tunnel-loss isolation verified: collector has no direct fallback.'
    ;;
  stop)
    if id "$collector" >/dev/null 2>&1; then sudo pkill -u "$collector" 2>/dev/null || true; fi
    if test -f "$private/openvpn.pid"; then sudo kill "$(cat "$private/openvpn.pid")" 2>/dev/null || true; fi
    sudo resolvectl revert "$interface" >/dev/null 2>&1 || true
    if id "$collector" >/dev/null 2>&1; then
      sudo iptables -D OUTPUT -m owner --uid-owner "$collector" -j PORTFOLIO_VPN 2>/dev/null || true
      sudo ip6tables -D OUTPUT -m owner --uid-owner "$collector" -j REJECT 2>/dev/null || true
    fi
    sudo iptables -F PORTFOLIO_VPN 2>/dev/null || true
    sudo iptables -X PORTFOLIO_VPN 2>/dev/null || true
    sudo iptables -D OUTPUT -p udp --dport 53 -j PORTFOLIO_DNS 2>/dev/null || true
    sudo iptables -D OUTPUT -p tcp --dport 53 -j PORTFOLIO_DNS 2>/dev/null || true
    sudo iptables -F PORTFOLIO_DNS 2>/dev/null || true
    sudo iptables -X PORTFOLIO_DNS 2>/dev/null || true
    sudo ip6tables -D OUTPUT -p udp --dport 53 ! -o lo -j REJECT 2>/dev/null || true
    sudo ip6tables -D OUTPUT -p tcp --dport 53 ! -o lo -j REJECT 2>/dev/null || true
    # Exact private directory below RUNNER_TEMP, never a repository directory.
    test "$private" = "$RUNNER_TEMP/portfolio-private" && sudo rm -rf -- "$private"
    echo 'Home tunnel stopped and temporary credentials removed.'
    ;;
  *) echo 'Usage: home_vpn.sh start|check|test-isolation|stop'; exit 2 ;;
esac
