import click
from ape import accounts, config, networks, project
from ape.cli import NetworkBoundCommand, account_option

DEPENDENCY = project.dependencies["openzeppelin"]["4.9.1"]


def convert_config(config):
    result = {}
    for item in config:
        if "contract_type" in item:
            result[item["contract_type"]] = item["address"]
        else:
            result.update(item)
    return result


def deploy_eth_contracts(deployer, child_address, config, eth_network):
    # Connect to the Ethereum network
    with eth_network.use_provider("infura"):

        token = project.TToken.deploy(
            100_000_000_000 * 10**18,
            sender=deployer,
        )

        threshold_staking = project.ThresholdStakingForTACoApplicationMock.deploy(
            sender=deployer,
        )

        taco_app = project.TACoApplication.deploy(
            token,
            threshold_staking,
            config["pre_min_authorization"],
            config["pre_min_operator_seconds"],
            config["reward_duration"],
            config["deauthorization_duration"],
            sender=deployer,
        )

        proxy_admin = DEPENDENCY.ProxyAdmin.deploy(sender=deployer)
        proxy = DEPENDENCY.TransparentUpgradeableProxy.deploy(
            taco_app.address,
            proxy_admin.address,
            taco_app.initialize.encode_input(),
            sender=deployer,
        )

        proxy_contract = project.TACoApplication.at(proxy.address)
        threshold_staking.setApplication(proxy_contract.address, sender=deployer)

        root = project.PolygonRoot.deploy(
            config["checkpoint_manager"],
            config["fx_root"],
            proxy_contract.address,
            child_address,
            sender=deployer,
            publish=False,
        )

        return root, proxy_contract, threshold_staking


def deploy_polygon_contracts(deployer, config, poly_network):
    # Connect to the Polygon network
    with poly_network.use_provider("infura"):
        polygon_child = project.PolygonChild.deploy(
            config["fx_child"],
            sender=deployer,
            publish=False,
        )

        TACoChild = project.TestnetTACoChildApplication.deploy(
            polygon_child.address,
            sender=deployer,
            publish=False,
        )
        proxy_admin = DEPENDENCY.ProxyAdmin.deploy(sender=deployer)
        proxy = DEPENDENCY.TransparentUpgradeableProxy.deploy(
            TACoChild.address,
            proxy_admin.address,
            b"",
            sender=deployer,
        )
        proxy_contract = project.TACoChildApplication.at(proxy.address)
        polygon_child.setChildApplication(proxy_contract.address, sender=deployer)

        coordinator = project.CoordinatorForTACoChildApplicationMock.deploy(
            proxy_contract.address, sender=deployer
        )
        proxy_contract.initialize(coordinator.address, [deployer], sender=deployer)

        return polygon_child, proxy_contract, coordinator


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
        poly_child, taco_child_app, coordinator = deploy_polygon_contracts(
            deployer, convert_config(poly_config), poly_network
        )
        root, taco_root_app, threshold_staking = deploy_eth_contracts(
            deployer, poly_child.address, convert_config(eth_config), eth_network
        )

        # Set the root contract address in the child contract
        with poly_network.use_provider("infura"):
            poly_child.setFxRootTunnel(root.address)
            taco_child_app.addUpdaters([poly_child.address])

    print("CHILD: {}".format(poly_child.address))
    print("TACo CHILD APP: {}".format(taco_child_app.address))
    print("COORDINATOR: {}".format(coordinator.address))
    print("ROOT: {}".format(root.address))
    print("THRESHOLD STAKING: {}".format(threshold_staking.address))
    print("TACO ROOT APP: {}".format(taco_root_app.address))
