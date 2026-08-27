#!/bin/sh
set -eu

RULE_PATH=/etc/udev/rules.d/71-speaky-input.rules

cat > "$RULE_PATH" <<'EOF'
# Speaky needs to observe press/release events for its configurable global
# hotkey.  uaccess grants the active desktop session access without adding
# users to the broad, persistent `input` group.
SUBSYSTEM=="input", KERNEL=="event*", TAG+="uaccess"
KERNEL=="uinput", TAG+="uaccess"
EOF

if command -v udevadm >/dev/null 2>&1; then
    udevadm control --reload-rules || true
    udevadm trigger --subsystem-match=input --action=change || true
fi

exit 0
