"""
This file is part of nucypher.

nucypher is free software: you can redistribute it and/or modify
it under the terms of the GNU Affero General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

nucypher is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU Affero General Public License for more details.

You should have received a copy of the GNU Affero General Public License
along with nucypher.  If not, see <https://www.gnu.org/licenses/>.
"""


import ape
from web3 import Web3

TOTAL_SUPPLY = Web3.to_wei(1_000_000_000, "ether")  # TODO NU(1_000_000_000, 'NU').to_units()


def test_create_token(project, accounts):
    creator = accounts[0]
    account1 = accounts[1]
    account2 = accounts[2]

    # Create an ERC20 token
    token = creator.deploy(project.NuCypherToken, TOTAL_SUPPLY)

    # Account balances
    assert TOTAL_SUPPLY == token.balanceOf(creator)
    assert 0 == token.balanceOf(account1)

    # Basic properties
    assert "NuCypher" == token.name()
    assert 18 == token.decimals()
    assert "NU" == token.symbol()

    # Cannot send ETH to the contract because there is no payable function
    with ape.reverts():
        creator.transfer(token, "100")

    # Can transfer tokens
    token.transfer(account1, 10000, sender=creator)
    assert 10000 == token.balanceOf(account1)
    assert TOTAL_SUPPLY - 10000 == token.balanceOf(creator)
    token.transfer(account2, 10, sender=account1)
    assert 10000 - 10 == token.balanceOf(account1)
    assert 10 == token.balanceOf(account2)
    token.transfer(token.address, 10, sender=account1)
    assert 10 == token.balanceOf(token.address)


def test_approve_and_call(project, accounts):
    creator = accounts[0]
    account1 = accounts[1]
    account2 = accounts[2]

    token = creator.deploy(project.NuCypherToken, TOTAL_SUPPLY)
    mock = creator.deploy(project.ReceiveApprovalMethodMock)

    # Approve some value and check allowance
    token.approve(account1, 100, sender=creator)
    assert 100 == token.allowance(creator, account1)
    assert 0 == token.allowance(creator, account2)
    assert 0 == token.allowance(account1, creator)
    assert 0 == token.allowance(account1, account2)
    assert 0 == token.allowance(account2, account1)

    # Use transferFrom with allowable value
    token.transferFrom(creator, account2, 50, sender=account1)
    assert 50 == token.balanceOf(account2)
    assert 50 == token.allowance(creator, account1)

    # The result of approveAndCall is increased allowance and method execution in the mock contract
    token.approveAndCall(mock.address, 25, Web3.to_bytes(111), sender=account1)
    assert 50 == token.balanceOf(account2)
    assert 50 == token.allowance(creator, account1)
    assert 25 == token.allowance(account1, mock.address)
    assert account1 == mock.sender()
    assert 25 == mock.value()
    assert token.address == mock.tokenContract()
    assert 111 == Web3.to_int(mock.extraData())

    # Can't approve non zero value
    with ape.reverts():
        token.approve(account1, 100, sender=creator)
    assert 50 == token.allowance(creator, account1)
    # Change to zero value and set new one
    token.approve(account1, 0, sender=creator)
    assert 0 == token.allowance(creator, account1)
    token.approve(account1, 100, sender=creator)
    assert 100 == token.allowance(creator, account1)

    # Decrease value
    token.approve(account1, 0, sender=creator)
    token.approve(account1, 40, sender=creator)
    assert 40 == token.allowance(creator, account1)
    token.approve(account1, 0, sender=creator)
    token.approve(account1, 50, sender=creator)
    assert 50 == token.allowance(creator, account1)
