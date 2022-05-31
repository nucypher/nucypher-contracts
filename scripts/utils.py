from brownie import accounts, network

LOCAL_BLOCKCHAIN_ENVIRONMENTS = ["development"]
PRODUCTION_ENVIRONMENTS = ["mainnet", "polygon-main"]
CURRENT_NETWORK = network.show_active()


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
