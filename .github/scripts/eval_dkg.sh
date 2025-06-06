#!/bin/bash

echo "Heartbeat: Evaluate Ritual"

echo "ECOSYSTEM: ${ECOSYSTEM}"
echo "NETWORK: ${NETWORK}"
echo "DOMAIN: ${DOMAIN}"

ape run evaluate_heartbeat \
--domain ${DOMAIN} \
--network ${ECOSYSTEM}:${NETWORK}:${RPC_PROVIDER}

echo "All Heartbeat Rituals Evaluated"
