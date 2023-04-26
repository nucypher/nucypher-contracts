from brownie import PolygonChild, PolygonRoot, StakeInfo, config, network
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

    return polygon_root.address


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
    stake_info = StakeInfo.deploy(
        polygon_child.address,
        {"from": deployer},
        publish_source=network_config.get("verify"),
    )

    return polygon_child.address, stake_info.address


def main(account_id=None):
    deployer = get_account(account_id)
    root_address = deploy_eth_contracts(deployer)
    child_address, stake_info_address = deploy_polygon_contracts(deployer)

    # Set the root contract address in the child contract
    # switch_network("polygon-test")
    tx = PolygonChild.at(child_address).setFxRootTunnel(root_address)
    tx.wait(1)
    tx = PolygonChild.at(child_address).setStakeInfoAddress(stake_info_address)
    tx.wait(1)

    # Set the child contract address in the root contract
    switch_network("goerli")
    tx = PolygonRoot.at(root_address).setFxChildTunnel(child_address, {"from": deployer})
    tx.wait(1)

    tx = PolygonRoot.at(root_address).updateOperator(
        "0x3B42d26E19FF860bC4dEbB920DD8caA53F93c600", 42069, {"from": deployer}
    )
    tx.wait(1)
