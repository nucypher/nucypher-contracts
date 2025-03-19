#!/bin/bash

echo "Heartbeat: Initiate Ritual"

echo "Network ${ECOSYSTEM}:${NETWORK}:${RPC_PROVIDER}"
echo "Authority: ${DKG_AUTHORITY_ADDRESS}"
echo "Access Controller: ${ACCESS_CONTROLLER}"
echo "Fee Model: ${FEE_MODEL}"
echo "Duration: ${DURATION}"

ape run initiate_ritual                           \
--heartbeat                                       \
--auto                                            \
--account automation                              \
--network ${ECOSYSTEM}:${NETWORK}:${RPC_PROVIDER} \
--domain ${DOMAIN}                                \
--access-controller ${ACCESS_CONTROLLER}          \
--authority ${DKG_AUTHORITY_ADDRESS}              \
--fee-model ${FEE_MODEL}                          \
--duration ${DURATION}                            \

echo "All Heartbeat Rituals Initiated"

