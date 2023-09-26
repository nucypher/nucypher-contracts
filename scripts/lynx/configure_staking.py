from ape import project
from ape.cli import get_user_selected_account
from deployment.constants import ARTIFACTS_DIR
from deployment.registry import read_registry

REGISTRY_FILEPATH = ARTIFACTS_DIR / "lynx" / "lynx-alpha-13-root-registry.json"


def main():
    registry_entries = read_registry(filepath=REGISTRY_FILEPATH)

    registry_contracts_dict = {
        registry_entry.contract_name: registry_entry for registry_entry in registry_entries
    }

    taco_application_entry = registry_contracts_dict[project.TACoApplication.contract_type.name]
    threshold_staking_entry = registry_contracts_dict[
        project.TestnetThresholdStaking.contract_type.name
    ]

    taco_application_contract = project.TACoApplication.at(taco_application_entry.contract_address)
    threshold_staking_contract = project.TestnetThresholdStaking.at(
        threshold_staking_entry.contract_address
    )

    deployer_account = get_user_selected_account()

    # Set up lynx stakes
    lynx_nodes = {
        "0xb15d5a4e2be34f4be154a1b08a94ab920ffd8a41": "0x890069745E9497C6f99Db68C4588deC5669F3d3E",
        "0x210eeac07542f815ebb6fd6689637d8ca2689392": "0xf48F720A2Ed237c24F5A7686543D90596bb8D44D",
        "0x48C8039c32F4c6f5cb206A5911C8Ae814929C16B": "0xce057adc39dcD1b3eA28661194E8963481CC48b2",
    }

    min_stake_size = taco_application_contract.minimumAuthorization()
    for staking_provider, operator in lynx_nodes.items():
        threshold_staking_contract.setRoles(staking_provider, sender=deployer_account)

        threshold_staking_contract.authorizationIncreased(
            staking_provider, 0, min_stake_size, sender=deployer_account
        )
