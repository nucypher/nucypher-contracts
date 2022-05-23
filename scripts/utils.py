from brownie import (
    NuCypherToken,
    StakingEscrow,
    ThresholdStakingForStakingEscrowMock,
    WorkLockForStakingEscrowMock,
    accounts,
    network,
)

LOCAL_BLOCKCHAIN_ENVIRONMENTS = ["development"]
PRODUCTION_ENVIRONMENTS = ["mainnet", "polygon-main"]
CURRENT_NETWORK = network.show_active()

def deploy_mocks(deployer):
    """This function should deploy nucypher_token and t_staking and return the
    corresponding contract addresses"""
    nucypher_token = NuCypherToken.deploy(1_000_000_000, {"from": deployer})
    t_staking = ThresholdStakingForStakingEscrowMock.deploy({"from": deployer})
    work_lock = WorkLockForStakingEscrowMock.deploy(nucypher_token, {"from": deployer})
    staking_escrow = StakingEscrow.deploy(nucypher_token, 0, 100_000, {"from": deployer})
    return nucypher_token, t_staking, work_lock, staking_escrow


def get_account(id):
    if CURRENT_NETWORK not in LOCAL_BLOCKCHAIN_ENVIRONMENTS:
        if id is None:
            raise ValueError("Must specify account id when deploying to production networks")
        else:
            return accounts.load(id)

    elif CURRENT_NETWORK in LOCAL_BLOCKCHAIN_ENVIRONMENTS:
        return accounts[0]
    else:
        return None
