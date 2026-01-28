// SPDX-License-Identifier: AGPL-3.0-or-later

pragma solidity ^0.8.0;

import "@openzeppelin-upgradeable/contracts/proxy/utils/Initializable.sol";
import "../contracts/coordination/SigningCoordinatorDispatcher.sol";
import "../contracts/coordination/ISigningCoordinatorChild.sol";

/**
 * @notice Mock contract for testing SigningCoordinatorDispatcher
 */
contract SigningCoordinatorMock is Initializable {
    SigningCoordinatorDispatcher public signingCoordinatorDispatcher;

    function setDispatcher(SigningCoordinatorDispatcher dispatcher) external {
        require(address(dispatcher).code.length > 0, "Dispatcher must be contract");
        signingCoordinatorDispatcher = dispatcher;
    }

    function callDispatch(uint256 chainId, bytes calldata callData) external {
        signingCoordinatorDispatcher.dispatch(chainId, callData);
    }
}

contract SigningCoordinatorChildMock is ISigningCoordinatorChild {
    function deployCohortMultiSig(uint32 cohortId, address[] calldata, uint16) external {
        emit CohortMultisigDeployed(cohortId, address(0));
    }

    function updateMultiSigParameters(
        uint32 cohortId,
        address[] calldata signers,
        uint16 threshold,
        bool clearSigners
    ) external {
        emit CohortMultisigUpdated(cohortId, address(0), signers, threshold, clearSigners);
    }
}

contract L1SenderMock {
    function sendData(address target, bytes calldata data) external {
        // solhint-disable-next-line avoid-low-level-calls
        (bool success, ) = target.call(data);
        require(success, "Execution failed");
    }
}
