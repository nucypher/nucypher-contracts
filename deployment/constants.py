from enum import IntEnum
from pathlib import Path

from ape import project

import deployment

#
# Filesystem
#

DEPLOYMENT_DIR = Path(deployment.__file__).parent
CONSTRUCTOR_PARAMS_DIR = DEPLOYMENT_DIR / "constructor_params"
ARTIFACTS_DIR = DEPLOYMENT_DIR / "artifacts"

#
# Domains
#

LYNX = "lynx"
TAPIR = "tapir"
MAINNET = "mainnet"

SUPPORTED_TACO_DOMAINS = [LYNX, TAPIR, MAINNET]

#
# Testnet
#

LYNX_NODES = {
    # staking provider -> operator
    "0xb15d5a4e2be34f4be154a1b08a94ab920ffd8a41": "0x890069745E9497C6f99Db68C4588deC5669F3d3E",
    "0x210eeac07542f815ebb6fd6689637d8ca2689392": "0xf48F720A2Ed237c24F5A7686543D90596bb8D44D",
    "0x48C8039c32F4c6f5cb206A5911C8Ae814929C16B": "0xce057adc39dcD1b3eA28661194E8963481CC48b2",
}

TAPIR_NODES = {
    # staking provider -> operator
    "0x05Be6D76d2282D24691E28E3Dc1c1A9709d70fa1": "0x91d12AB1EffBa82A4756ea029D40DE3fCD8f0255",
    "0xd274f0060256c186479f2b9f51615003cbcd19E6": "0xB6e188a88948d2d9bB5A3Eb05B7aC96A85A8BF07",
    "0xA7165c0229544c84b417e53a1D3ab717EA4b4587": "0x5d01059e669081861F8D9A4082a3A2ed6EB46A4B",
    "0x18F3a9ae64339E4FcfeBe1ac89Bc51aC3c83C22E": "0x131617ed5894Fe9f5A4B97a276ec99430A0a8B23",
    "0xcbE2F626d84c556AbA674FABBbBDdbED6B39d87b": "0xb057B982fB575509047e90cf5087c9B863a2022d",
}

TESTNET_PROVIDERS = {
    LYNX: list(sorted(LYNX_NODES)),
    TAPIR: list(sorted(TAPIR_NODES))
}

#
# Contracts
#

OZ_DEPENDENCY = project.dependencies["openzeppelin"]["5.0.0"]

# EIP1967 Admin slot - https://eips.ethereum.org/EIPS/eip-1967#admin-address
EIP1967_ADMIN_SLOT = 0xB53127684A568B3173AE13B9F8A6016E243E63B6E8EE1178D6A717850B5D6103

ACCESS_CONTROLLERS = ["GlobalAllowList", "OpenAccessAuthorizer", "ManagedAllowList"]

#
# Sampling
#

PORTER_SAMPLING_ENDPOINTS = {
    MAINNET: "https://porter.nucypher.io/bucket_sampling",
    LYNX: "https://porter-lynx.nucypher.io/get_ursulas",
    TAPIR: "https://porter-tapir.nucypher.io/get_ursulas",
}

#
# Domain Seednodes
#

NETWORK_SEEDNODE_STATUS_JSON_URI = {
    MAINNET: "https://mainnet.nucypher.network:9151/status?json=true",
    LYNX: "https://lynx.nucypher.network:9151/status?json=true",
    TAPIR: "https://tapir.nucypher.network:9151/status?json=true",
}

#
# DKG Ritual states as defined in the Coordinator contract
#


class RitualState(IntEnum):
    NON_INITIATED = 0
    DKG_AWAITING_TRANSCRIPTS = 1
    DKG_AWAITING_AGGREGATIONS = 2
    DKG_TIMEOUT = 3
    DKG_INVALID = 4
    ACTIVE = 5
    EXPIRED = 6


HEARTBEAT_ARTIFACT_FILENAME = "heartbeat-rituals.json"
