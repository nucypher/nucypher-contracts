import os
from pathlib import Path

from ape import accounts, project
from scripts.constants import (
    CURRENT_NETWORK,
    ETHERSCAN_API_KEY_ENVVAR,
    LOCAL_BLOCKCHAIN_ENVIRONMENTS,
)
from web3 import Web3


def deploy_mocks(deployer):
    """This function should deploy nucypher_token and t_staking and return the
    corresponding contract addresses"""
    nucypher_token = project.NuCypherToken.deploy(1_000_000_000, sender=deployer)
    t_staking_for_escrow = project.ThresholdStakingForStakingEscrowMock.deploy(sender=deployer)
    t_staking_for_taco = project.ThresholdStakingForTACoApplicationMock.deploy(sender=deployer)
    total_supply = Web3.to_wei(10_000_000_000, "ether")
    t_token = project.TToken.deploy(total_supply, sender=deployer)
    work_lock = project.WorkLockForStakingEscrowMock.deploy(nucypher_token, sender=deployer)
    staking_escrow = project.StakingEscrow.deploy(
        nucypher_token, work_lock, t_staking_for_escrow, sender=deployer
    )
    return (
        nucypher_token,
        t_staking_for_escrow,
        t_staking_for_taco,
        work_lock,
        staking_escrow,
        t_token,
    )


def get_account(_id):
    if CURRENT_NETWORK not in LOCAL_BLOCKCHAIN_ENVIRONMENTS:
        if _id is None:
            raise ValueError("Must specify account id when deploying to production networks")
        else:
            return accounts.load(_id)

    elif CURRENT_NETWORK in LOCAL_BLOCKCHAIN_ENVIRONMENTS:
        return accounts.test_accounts[0]
    else:
        return None


def check_registry_filepath(registry_filepath: Path) -> None:
    """
    Checks that the registry_filepath does not exist,
    and that its parent directory does exist.
    """
    if registry_filepath.exists():
        raise FileExistsError(f"Registry file already exists at {registry_filepath}")
    if not registry_filepath.parent.exists():
        raise FileNotFoundError(f"Parent directory of {registry_filepath} does not exist.")


def check_etherscan_plugin() -> None:
    """Checks that the ape-etherscan plugin is installed and that the ETHERSCAN_API_KEY is set."""
    if CURRENT_NETWORK in LOCAL_BLOCKCHAIN_ENVIRONMENTS:
        # unnecessary for local deployment
        return

    try:
        import ape_etherscan  # noqa: F401
    except ImportError:
        raise ImportError("Please install the ape-etherscan plugin to use this script.")

    api_key = os.environ.get(ETHERSCAN_API_KEY_ENVVAR)
    if not api_key:
        raise ValueError(f"{ETHERSCAN_API_KEY_ENVVAR} is not set.")
    if not len(api_key) == 34:
        raise ValueError(f"{ETHERSCAN_API_KEY_ENVVAR} is not valid.")
