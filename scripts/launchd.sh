#!/usr/bin/env bash
# LaunchAgents that publish this Mac's instance at https://24dms.ru:
#   local.extract-agent.app     — scripts/serve.sh (API + SPA on 127.0.0.1:8080)
#   local.extract-agent.tunnel  — autossh reverse tunnel → VPS 127.0.0.1:18080 (nginx in front)
#   local.extract-agent.awake   — caffeinate: no idle sleep while on power
# All three start at login and are restarted by launchd if they exit.
#   scripts/launchd.sh install | uninstall | restart | status
set -euo pipefail
cd "$(dirname "$0")/.."

REPO="$(pwd)"
AGENTS="$HOME/Library/LaunchAgents"
LOGS="$HOME/Library/Logs/extract-agent"
VPS="${VPS:-tunnel@72.56.107.180}"
TUNNEL_KEY="${TUNNEL_KEY:-$HOME/.ssh/extract_agent_tunnel}"
# launchd starts with a bare PATH: docker, node/npm, autossh and optional codex CLI live elsewhere
LAUNCH_PATH="$HOME/.local/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"
LABELS=(local.extract-agent.app local.extract-agent.tunnel local.extract-agent.awake)

plist() {  # label, then program arguments
  local label="$1"; shift
  local args=""
  for a in "$@"; do args+="    <string>${a}</string>"$'\n'; done
  cat > "$AGENTS/$label.plist" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>${label}</string>
  <key>ProgramArguments</key>
  <array>
${args}  </array>
  <key>WorkingDirectory</key><string>${REPO}</string>
  <key>EnvironmentVariables</key>
  <dict>
    <key>PATH</key><string>${LAUNCH_PATH}</string>
    <key>SKIP_BUILD</key><string>1</string>
    <key>AUTOSSH_GATETIME</key><string>0</string>
  </dict>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>ThrottleInterval</key><integer>30</integer>
  <key>StandardOutPath</key><string>${LOGS}/${label#local.extract-agent.}.log</string>
  <key>StandardErrorPath</key><string>${LOGS}/${label#local.extract-agent.}.log</string>
</dict>
</plist>
EOF
}

case "${1:-status}" in
  install)
    mkdir -p "$AGENTS" "$LOGS"
    plist local.extract-agent.app "$REPO/scripts/serve.sh"
    plist local.extract-agent.tunnel /opt/homebrew/bin/autossh -M 0 -N \
      -i "$TUNNEL_KEY" -o IdentitiesOnly=yes -o BatchMode=yes \
      -o ServerAliveInterval=30 -o ServerAliveCountMax=3 -o ExitOnForwardFailure=yes \
      -R 127.0.0.1:18080:127.0.0.1:8080 "$VPS"
    plist local.extract-agent.awake /usr/bin/caffeinate -i -s
    for l in "${LABELS[@]}"; do
      launchctl bootout "gui/$UID/$l" 2>/dev/null || true
      launchctl bootstrap "gui/$UID" "$AGENTS/$l.plist"
    done
    echo "installed; logs in $LOGS"
    ;;
  uninstall)
    for l in "${LABELS[@]}"; do
      launchctl bootout "gui/$UID/$l" 2>/dev/null || true
      rm -f "$AGENTS/$l.plist"
    done
    echo "uninstalled"
    ;;
  restart)
    for l in "${LABELS[@]}"; do launchctl kickstart -k "gui/$UID/$l"; done
    ;;
  status)
    for l in "${LABELS[@]}"; do
      printf "%-28s %s\n" "$l" "$(launchctl print "gui/$UID/$l" 2>/dev/null | awk '/^\tstate =/{print $3; exit}' || true)"
    done
    ;;
  *) echo "usage: $0 install|uninstall|restart|status" >&2; exit 2 ;;
esac
