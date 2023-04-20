from brownie import PolygonChild, PolygonRoot, accounts, config, network


def deploy_eth_contracts():
    # Connect to the Ethereum network
    network.connect("goerli")
    network_config = config["networks"]["goerli"]

    # Deploy the FxStateRootTunnel contract
    polygon_root = PolygonRoot.deploy(
        network_config.get("check_point_manager"),
        network_config.get("fx_root"),
        {"from": accounts[0]},
    )

    # Print the address of the deployed contract
    print("FxStateRootTunnel deployed at:", polygon_root.address)
    return polygon_root.address


def deploy_polygon_contracts():
    # Connect to the Polygon network
    network.connect("polygon-test")
    network_config = config["networks"]["polygon-test"]

    # Deploy the FxStateChildTunnel contract
    child_tunnel = PolygonChild.deploy(network_config.get("fx_child"), {"from": accounts[0]})

    # Print the address of the deployed contract
    print("FxStateChildTunnel deployed at:", child_tunnel.address)


polygon_root_address = deploy_eth_contracts()
deploy_polygon_contracts(polygon_root_address)
