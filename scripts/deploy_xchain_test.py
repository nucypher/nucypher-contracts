from brownie import PolygonChild, PolygonRoot, config, network
from scripts.utils import get_account


def switch_network(network_name):
    network.disconnect()
    network.connect(network_name)


def deploy_eth_contracts(deployer):
    # Connect to the Ethereum network
    switch_network("goerli")
    network_config = config["networks"]["goerli"]

    # Deploy the FxStateRootTunnel contract
    polygon_root = PolygonRoot.deploy(
        network_config.get("check_point_manager"),
        network_config.get("fx_root"),
        {"from": deployer},
        publish_source=network_config.get("verify"),
    )

    # Print the address of the deployed contract
    print("PolygonRoot deployed at:", polygon_root.address)
    return polygon_root


def deploy_polygon_contracts(deployer):
    # Connect to the Polygon network
    switch_network("polygon-test")
    network_config = config["networks"]["polygon-test"]

    # Deploy the FxStateChildTunnel contract
    polygon_child = PolygonChild.deploy(
        network_config.get("fx_child"),
        {"from": deployer},
        publish_source=network_config.get("verify"),
    )

    # Print the address of the deployed contract
    print("PolygonChild deployed at:", polygon_child.address)
    return polygon_child


def main(account_id=None):
    deployer = get_account(account_id)
    deploy_eth_contracts(deployer)
    deploy_polygon_contracts(deployer)
