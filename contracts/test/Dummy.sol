// SPDX-License-Identifier: AGPL-3.0-or-later

pragma solidity ^0.8.0;

contract Dummy {
    // solhint-disable-next-line no-empty-blocks
    receive() external payable {}

    // solhint-disable-next-line no-empty-blocks
    fallback() external payable {}
}
