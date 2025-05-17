// SPDX-License-Identifier: AGPL-3.0-or-later

pragma solidity ^0.8.0;

import "@openzeppelin/contracts/access/Ownable.sol";
import "./ISigningCoordinatorChild.sol";
import "./IL1Sender.sol";

contract SigningCoordinatorDispatcher is Ownable {
    struct DispatchTarget {
        address l1Sender;
        address signingCoordinatorChild;
    }

    address public immutable signingCoordinator;
    mapping(uint256 => DispatchTarget) public dispatchMap;

    constructor(address _signingCoordinator) Ownable(msg.sender) {
        require(_signingCoordinator.code.length > 0, "Signing app must be contract");
        signingCoordinator = _signingCoordinator;
    }

    function register(
        uint256 chainId,
        address l1Sender,
        address signingCoordinatorChild
    ) external onlyOwner {
        require(chainId > 0, "Invalid chain ID");
        if (chainId != block.chainid) {
            require(l1Sender != address(0), "Invalid L1 sender");
        }
        require(signingCoordinatorChild != address(0), "Invalid target");
        dispatchMap[chainId] = DispatchTarget(l1Sender, signingCoordinatorChild);
    }

    function unregister(uint256 chainId) external onlyOwner {
        require(chainId != 0, "Invalid chain ID");
        delete dispatchMap[chainId];
    }

    function dispatch(uint256 chainId, bytes calldata callData) external {
        require(signingCoordinator == msg.sender, "Unauthorized caller");
        DispatchTarget memory target = dispatchMap[chainId];
        require(target.signingCoordinatorChild != address(0), "Unknown target");
        if (chainId == block.chainid) {
            // Same chain → direct call
            // solhint-disable-next-line avoid-low-level-calls
            (bool success, ) = target.signingCoordinatorChild.call(callData);
            require(success, "Local call failed");
        } else {
            // Cross-chain (e.g., L1 → L2)
            require(target.l1Sender != address(0), "Unknown L1 sender");
            IL1Sender(target.l1Sender).sendData(target.signingCoordinatorChild, callData);
        }
    }
}
