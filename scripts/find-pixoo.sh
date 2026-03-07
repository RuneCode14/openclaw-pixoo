#!/usr/bin/env bash
# Find Divoom Pixoo devices on the local network.
#
# Scans common ports and probes each host for the Divoom HTTP API.
# Usage: ./find-pixoo.sh [subnet]
# Example: ./find-pixoo.sh 192.168.1.0/24

set -euo pipefail

SUBNET="${1:-}"

# Auto-detect subnet if not provided
if [ -z "$SUBNET" ]; then
    # Get the default gateway's subnet
    GATEWAY_IP=$(ip route | awk '/default/ {print $3}' 2>/dev/null || route -n get default 2>/dev/null | awk '/gateway:/ {print $2}')
    if [ -z "$GATEWAY_IP" ]; then
        echo "Could not detect network. Provide subnet: $0 192.168.1.0/24"
        exit 1
    fi
    # Derive /24 subnet from gateway
    SUBNET=$(echo "$GATEWAY_IP" | sed 's/\.[0-9]*$/.0\/24/')
    echo "Auto-detected subnet: $SUBNET"
fi

echo "Scanning $SUBNET for Pixoo devices..."
echo ""

FOUND=0

# Scan for hosts with port 80 open
HOSTS=$(nmap -sn "$SUBNET" -T4 2>/dev/null | grep "report for" | awk '{print $NF}' | tr -d '()')

for HOST in $HOSTS; do
    # Quick check if port 80 is open
    if ! timeout 1 bash -c "echo >/dev/tcp/$HOST/80" 2>/dev/null; then
        continue
    fi

    # Probe for Divoom API
    RESPONSE=$(curl -s -m 2 -X POST "http://$HOST:80/post" \
        -H 'Content-Type: application/json' \
        -d '{"Command":"Channel/GetIndex"}' 2>/dev/null || true)

    if echo "$RESPONSE" | grep -q '"error_code"' 2>/dev/null; then
        # It's a Divoom device! Get more info
        TIME_RESPONSE=$(curl -s -m 2 -X POST "http://$HOST:80/post" \
            -H 'Content-Type: application/json' \
            -d '{"Command":"Device/GetDeviceTime"}' 2>/dev/null || true)

        CONF_RESPONSE=$(curl -s -m 2 -X POST "http://$HOST:80/post" \
            -H 'Content-Type: application/json' \
            -d '{"Command":"Channel/GetAllConf"}' 2>/dev/null || true)

        BRIGHTNESS=$(echo "$CONF_RESPONSE" | grep -o '"Brightness":[0-9]*' | cut -d: -f2)
        CHANNEL=$(echo "$RESPONSE" | grep -o '"SelectIndex":[0-9]*' | cut -d: -f2)

        echo "✅ Found Pixoo at: $HOST"
        echo "   Channel: $CHANNEL"
        echo "   Brightness: ${BRIGHTNESS:-unknown}"
        echo "   API: http://$HOST:80/post"
        echo ""
        FOUND=$((FOUND + 1))
    fi
done

if [ "$FOUND" -eq 0 ]; then
    echo "No Pixoo devices found on $SUBNET"
    echo ""
    echo "Troubleshooting:"
    echo "  - Is the Pixoo powered on and connected to WiFi?"
    echo "  - Is it on the same network as this machine?"
    echo "  - Try the Divoom app to check the device IP"
    exit 1
else
    echo "Found $FOUND Pixoo device(s)"
fi
