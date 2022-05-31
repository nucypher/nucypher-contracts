from brownie import (
    NuCypherToken,
    StakingEscrow,
    ThresholdStakingForStakingEscrowMock,
    ThresholdStakingForPREApplicationMock,
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
    t_staking_for_escrow = ThresholdStakingForStakingEscrowMock.deploy({"from": deployer})
    t_staking_for_pre = ThresholdStakingForPREApplicationMock.deploy({"from": deployer})
    work_lock = WorkLockForStakingEscrowMock.deploy(nucypher_token, {"from": deployer})
    staking_escrow = StakingEscrow.deploy(
        nucypher_token, work_lock, t_staking_for_escrow, {"from": deployer}
    )
    return nucypher_token, t_staking_for_escrow, t_staking_for_pre, work_lock, staking_escrow


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
