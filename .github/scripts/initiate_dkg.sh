
echo "ECOSYSTEM: ${ECOSYSTEM}"
echo "NETWORK: ${NETWORK}"
echo "RPC_PROVIDER: ${RPC_PROVIDER}"
echo "DOMAIN: ${DOMAIN}"
echo "DURATION: ${DURATION}"
echo "NUM_NODES: ${NUM_NODES}"
echo "DKG_AUTHORITY_ADDRESS: ${DKG_AUTHORITY_ADDRESS}"
echo "MIN_VERSION: ${MIN_VERSION}"
echo "ACCESS_CONTROLLER: ${ACCESS_CONTROLLER}"
echo "FEE_MODEL: ${FEE_MODEL}"

ape run initiate_ritual \
--autosign \
--account automation \
--network ${ECOSYSTEM}:${NETWORK}:${RPC_PROVIDER} \
--domain ${DOMAIN} \
--duration ${DURATION} \
--access-controller ${ACCESS_CONTROLLER} \
--fee-model ${FEE_MODEL} \
--authority ${DKG_AUTHORITY_ADDRESS} \
--min-version ${MIN_VERSION} \
--num-nodes ${NUM_NODES}
