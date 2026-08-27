#!/bin/sh
set -eu

if [ "${1:-}" = remove ] || [ "${1:-}" = purge ]; then
    rm -f /etc/udev/rules.d/71-speaky-input.rules
    if command -v udevadm >/dev/null 2>&1; then
        udevadm control --reload-rules || true
    fi
fi

exit 0
