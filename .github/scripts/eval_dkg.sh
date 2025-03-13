echo "ECOSYSTEM: ${ECOSYSTEM}"
echo "NETWORK: ${NETWORK}"
echo "DOMAIN: ${DOMAIN}"

ape run evaluate_heartbeat \
--artifact rituals.json \
--domain ${DOMAIN} \
--network ${ECOSYSTEM}:${NETWORK}:${RPC_PROVIDER}
