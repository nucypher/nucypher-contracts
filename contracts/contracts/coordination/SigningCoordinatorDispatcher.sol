// SPDX-License-Identifier: AGPL-3.0-or-later

pragma solidity ^0.8.0;

import "./ICrossDomainMessenger.sol";

contract SigningCoordinatorDispatcher {
    struct Target {
        address xDomainSender;
        address targetAddress;
    }

    mapping(uint256 => Target) public dispatchMap;

    function register(uint256 chainId, address xDomainSender, address targetAddress) external {
        require(chainId != 0, "Invalid chain ID");
        if (chainId != block.chainid) {
            require(xDomainSender != address(0), "Invalid L1 sender");
        }
        require(targetAddress != address(0), "Unknown target");
        dispatchMap[chainId] = Target(xDomainSender, targetAddress);
    }

    function dispatch(uint256 chainId, bytes calldata callData, uint32 gasLimit) external {
        Target memory target = dispatchMap[chainId];
        require(target.targetAddress != address(0), "Unknown target");

        if (chainId == block.chainid) {
            // Same chain → direct call
            // solhint-disable-next-line avoid-low-level-calls
            (bool success, ) = target.targetAddress.call(callData);
            require(success, "Local call failed");
        } else {
            // Cross-chain (e.g., L1 → L2)
            require(target.xDomainSender != address(0), "Unknown L1 sender");
            ICrossDomainMessenger(target.xDomainSender).sendMessage(
                target.targetAddress,
                callData,
                gasLimit
            );
        }
    }
}
