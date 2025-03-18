
echo "ECOSYSTEM: ${ECOSYSTEM}"
echo "NETWORK: ${NETWORK}"
echo "RPC_PROVIDER: ${RPC_PROVIDER}"
echo "DOMAIN: ${DOMAIN}"
echo "DKG_AUTHORITY_ADDRESS: ${DKG_AUTHORITY_ADDRESS}"
echo "ACCESS_CONTROLLER: ${ACCESS_CONTROLLER}"
echo "FEE_MODEL: ${FEE_MODEL}"
echo "DURATION: ${DURATION}"

echo "Current directory: $(pwd)"

ape run initiate_ritual \
--autosign \
--account automation \
--network ${ECOSYSTEM}:${NETWORK}:${RPC_PROVIDER} \
--domain ${DOMAIN} \
--access-controller ${ACCESS_CONTROLLER} \
--fee-model ${FEE_MODEL} \
--authority ${DKG_AUTHORITY_ADDRESS} \
--heartbeat \
--duration ${DURATION}
