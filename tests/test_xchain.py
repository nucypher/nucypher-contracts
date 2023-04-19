import pytest
from brownie import EthCrossChainMessenger, PolygonCrossChainMessenger, accounts


@pytest.fixture(scope="module")
def eth_messenger():
    chain_id = 1  # Ethereum Mainnet
    root_chain_manager = (
        "0xA0c68C638235ee32657e8f720a23ceC1bFc77C77"  # Address of the RootChainManager on Ethereum
    )
    messenger = EthCrossChainMessenger.deploy(root_chain_manager, chain_id, {"from": accounts[0]})
    messenger.addMessageSenderRole(accounts[0], {"from": accounts[0]})
    return messenger


@pytest.fixture(scope="module")
def polygon_messenger():
    chain_id = 137  # Polygon Mainnet
    root_chain_manager = (
        "0xBbD7cBFA79faee899Eaf900F13C9065bF03B1A74"  # Address of the RootChainManager on Polygon
    )
    messenger = PolygonCrossChainMessenger.deploy(
        root_chain_manager, chain_id, {"from": accounts[0]}
    )
    messenger.addMessageSenderRole(accounts[0], {"from": accounts[0]})
    return messenger


def test_cross_chain_messaging(eth_messenger, polygon_messenger):
    # Send a message from the Ethereum contract to the Polygon contract
    message = "Hello from Ethereum"
    polygon_contract_address = "0x123abc..."  # Address of the recipient contract on Polygon
    eth_messenger.sendMessageToPolygon(
        polygon_contract_address, message.encode("utf-8"), {"from": accounts[0]}
    )

    # Verify that the message was received on the Polygon contract
    assert polygon_messenger.messageReceived() == message

    # Send a message from the Polygon contract to the Ethereum contract
    message = "Hello from Polygon"
    eth_contract_address = "0x456def..."  # Address of the recipient contract on Ethereum
    polygon_messenger.sendMessageToEth(
        eth_contract_address, message.encode("utf-8"), {"from": accounts[0]}
    )

    # Verify that the message was received on the Ethereum contract
    assert eth_messenger.messageReceived() == message
