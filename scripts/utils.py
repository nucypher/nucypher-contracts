from ape import accounts, config, networks, project
from web3 import Web3

LOCAL_BLOCKCHAIN_ENVIRONMENTS = ["local"]
PRODUCTION_ENVIRONMENTS = ["mainnet", "polygon-main"]
CURRENT_NETWORK = networks.network.name
DEPLOYMENTS_CONFIG = config.get_config("deployments")["ethereum"][CURRENT_NETWORK][0]


def deploy_mocks(deployer):
    """This function should deploy nucypher_token and t_staking and return the
    corresponding contract addresses"""
    nucypher_token = project.NuCypherToken.deploy(1_000_000_000, sender=deployer)
    t_staking_for_escrow = project.ThresholdStakingForStakingEscrowMock.deploy(sender=deployer)
    t_staking_for_pre = project.ThresholdStakingForPREApplicationMock.deploy(sender=deployer)
    total_supply = Web3.to_wei(10_000_000_000, "ether")
    t_token = project.TToken.deploy(total_supply, sender=deployer)
    work_lock = project.WorkLockForStakingEscrowMock.deploy(nucypher_token, sender=deployer)
    staking_escrow = project.StakingEscrow.deploy(
        nucypher_token, work_lock, t_staking_for_escrow, sender=deployer
    )
    return (
        nucypher_token,
        t_staking_for_escrow,
        t_staking_for_pre,
        work_lock,
        staking_escrow,
        t_token,
    )


def get_account(id):
    if CURRENT_NETWORK not in LOCAL_BLOCKCHAIN_ENVIRONMENTS:
        if id is None:
            raise ValueError("Must specify account id when deploying to production networks")
        else:
            return accounts.load(id)

    elif CURRENT_NETWORK in LOCAL_BLOCKCHAIN_ENVIRONMENTS:
        return accounts.test_accounts[0]
    else:
        return None
