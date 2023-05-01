from ape import accounts, config, networks, project


def deploy_eth_contracts(deployer):
    # Connect to the Ethereum network
    with networks.ethereum.goerli.use_provider("infura"):
        DEPLOYMENTS_CONFIG = config.get_config("deployments")["ethereum"]["goerli"][0]

        # Deploy the FxStateRootTunnel contract
        polygon_root = project.PolygonRoot.deploy(
            DEPLOYMENTS_CONFIG.get("checkpoint_manager"),
            DEPLOYMENTS_CONFIG.get("fx_root"),
            sender=deployer,
            publish=DEPLOYMENTS_CONFIG.get("verify"),
        )

        return polygon_root


def deploy_polygon_contracts(deployer):
    # Connect to the Polygon network
    with networks.polygon.mumbai.use_provider("infura"):
        DEPLOYMENTS_CONFIG = config.get_config("deployments")["polygon"]["mumbai"][0]

        # Deploy the FxStateChildTunnel contract
        polygon_child = project.PolygonChild.deploy(
            DEPLOYMENTS_CONFIG.get("fx_child"),
            sender=deployer,
        )
        stake_info = project.StakeInfo.deploy(
            polygon_child.address,
            [deployer.address, polygon_child.address],
            sender=deployer,
        )

        return polygon_child, stake_info


def main(account_id=None):
    deployer = accounts.load("TGoerli")
    with accounts.use_sender(deployer):
        root = deploy_eth_contracts(deployer)
        child, stake_info = deploy_polygon_contracts(deployer)

        # Set the root contract address in the child contract
        # switch_network("polygon-test")
        with networks.polygon.mumbai.use_provider("infura"):
            child.setFxRootTunnel(root.address)
            child.setStakeInfoAddress(stake_info.address)

        # Set the child contract address in the root contract
        with networks.ethereum.goerli.use_provider("infura"):
            root.setFxChildTunnel(child.address)
            root.updateOperator(
                "0x3B42d26E19FF860bC4dEbB920DD8caA53F93c600",
                "0x3B42d26E19FF860bC4dEbB920DD8caA53F93c600",
            )
