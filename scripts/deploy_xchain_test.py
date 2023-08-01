import click
from ape import accounts, config, networks, project
from ape.cli import NetworkBoundCommand, account_option


def convert_config(config):
    result = {}
    for item in config:
        if "contract_type" in item:
            result[item["contract_type"]] = item["address"]
        else:
            result.update(item)
    return result


def deploy_eth_contracts(deployer, source, child_address, config, eth_network):
    # Connect to the Ethereum network
    with eth_network.use_provider("infura"):
        polygon_root = project.PolygonRoot.deploy(
            config["checkpoint_manager"],
            config["fx_root"],
            source,
            child_address,
            sender=deployer,
            publish=False,
        )

        return polygon_root


def deploy_polygon_contracts(deployer, config, poly_network):
    # Connect to the Polygon network
    with poly_network.use_provider("infura"):
        stake_info = project.StakeInfo.deploy(
            [deployer.address],
            sender=deployer,
            publish=False,
        )

        polygon_child = project.PolygonChild.deploy(
            config["fx_child"],
            stake_info.address,
            sender=deployer,
            publish=False,
        )

        return polygon_child, stake_info


# TODO: Figure out better way to retrieve the TACo app contract address
@click.command(cls=NetworkBoundCommand)
@click.option("--network_type", type=click.Choice(["mainnet", "testnet"]))
@account_option()
def cli(network_type, account):
    deployer = account
    if network_type == "mainnet":
        eth_config = config.get_config("deployments")["ethereum"]["mainnet"]
        poly_config = config.get_config("deployments")["polygon"]["mainnet"]
        eth_network = networks.ethereum.mainnet
        poly_network = networks.polygon.mainnet
    elif network_type == "testnet":
        eth_config = config.get_config("deployments")["ethereum"]["goerli"]
        poly_config = config.get_config("deployments")["polygon"]["mumbai"]
        eth_network = networks.ethereum.goerli
        poly_network = networks.polygon.mumbai

    print("Deployer: {}".format(deployer))
    print("ETH CONFIG: {}".format(eth_config))
    print("POLYGON CONFIG: {}".format(poly_config))

    with accounts.use_sender(deployer):
        child, stake_info = deploy_polygon_contracts(
            deployer, convert_config(poly_config), poly_network
        )
        root = deploy_eth_contracts(
            deployer, deployer.address, child.address, convert_config(eth_config), eth_network
        )

        # Set the root contract address in the child contract
        with poly_network.use_provider("infura"):
            child.setFxRootTunnel(root.address)
            stake_info.addUpdaters([child.address])

    print("CHILD: {}".format(child.address))
    print("STAKE INFO: {}".format(stake_info.address))
    print("ROOT: {}".format(root.address))
