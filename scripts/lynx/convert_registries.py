#!/usr/bin/python3


from eth_typing import ChecksumAddress, HexAddress, HexStr

from deployment.constants import ARTIFACTS_DIR
from deployment.legacy import convert_legacy_registry

DEPLOYER = ChecksumAddress(HexAddress(HexStr("0x3B42d26E19FF860bC4dEbB920DD8caA53F93c600")))
LEGACY_ROOT_REGISTRY_FILEPATH = ARTIFACTS_DIR / "lynx" / "lynx-alpha-13-root-registry.json"
LEGACY_CHILD_REGISTRY_FILEPATH = ARTIFACTS_DIR / "lynx" / "lynx-alpha-13-child-registry.json"
OUTPUT_FILEPATH = ARTIFACTS_DIR / "lynx.json"


def main():
    if OUTPUT_FILEPATH.exists():
        raise FileExistsError(f"Output filepath already exists at {OUTPUT_FILEPATH}")
    for chain_id, filepath in (
        (80002, LEGACY_CHILD_REGISTRY_FILEPATH),
        (5, LEGACY_ROOT_REGISTRY_FILEPATH),
    ):
        convert_legacy_registry(
            legacy_filepath=filepath,
            output_filepath=OUTPUT_FILEPATH,
            chain_id=chain_id,
        )
