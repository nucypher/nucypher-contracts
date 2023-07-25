from ape import accounts, config, networks, project


def deploy_eth_contracts(deployer, source, child_address):
    # Connect to the Ethereum network
    with networks.ethereum.goerli.use_provider("infura"):
        DEPLOYMENTS_CONFIG = config.get_config("deployments")["ethereum"]["goerli"][0]

        polygon_root = project.PolygonRoot.deploy(
            DEPLOYMENTS_CONFIG.get("checkpoint_manager"),
            DEPLOYMENTS_CONFIG.get("fx_root"),
            source,
            child_address,
            sender=deployer,
            publish=DEPLOYMENTS_CONFIG.get("verify"),
        )

        return polygon_root


def deploy_polygon_contracts(deployer):
    # Connect to the Polygon network
    with networks.polygon.mumbai.use_provider("infura"):
        DEPLOYMENTS_CONFIG = config.get_config("deployments")["polygon"]["mumbai"][0]

        stake_info = project.StakeInfo.deploy(
            [deployer.address, polygon_child.address],
            sender=deployer,
            publish=DEPLOYMENTS_CONFIG.get("verify"),
        )

        polygon_child = project.PolygonChild.deploy(
            DEPLOYMENTS_CONFIG.get("fx_child"),
            stake_info.address,
            sender=deployer,
            publish=DEPLOYMENTS_CONFIG.get("verify"),
        )


        return polygon_child, stake_info

# TODO: Figure out better way to retrieve the TACo app contract address
def main(taco_app, account_id=None):
    deployer = accounts.load("TGoerli")
    with accounts.use_sender(deployer):
        child, _ = deploy_polygon_contracts(deployer)
        root = deploy_eth_contracts(deployer, child.address, taco_app)

        # Set the root contract address in the child contract
        with networks.polygon.mumbai.use_provider("infura"):
            child.setFxRootTunnel(root.address)
