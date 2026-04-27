// SPDX-License-Identifier: AGPL-3.0-or-later

pragma solidity ^0.8.0;

import "@openzeppelin-upgradeable/contracts/proxy/utils/Initializable.sol";
import "../contracts/coordination/SigningCoordinator.sol";
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

contract MockSigningCoordinatorForInitiator {
    SigningCoordinator.SigningCohort[] public signingCohorts;
    mapping(uint32 => SigningCoordinator.SigningCohortState) public cohortStates;

    function getSigningCohortState(
        uint32 _cohortId
    ) external view returns (SigningCoordinator.SigningCohortState) {
        if (_cohortId >= signingCohorts.length) {
            return SigningCoordinator.SigningCohortState.NON_INITIATED;
        }
        return cohortStates[_cohortId];
    }

    function setCohortState(
        uint32 _cohortId,
        SigningCoordinator.SigningCohortState _state
    ) external {
        cohortStates[_cohortId] = _state;
    }

    function isCohortActive(uint32 cohortId) external view returns (bool) {
        return cohortStates[cohortId] == SigningCoordinator.SigningCohortState.ACTIVE;
    }

    function getAuthority(uint32 cohortId) external view returns (address) {
        return signingCohorts[cohortId].authority;
    }

    function getChains(uint32 cohortId) external view returns (uint256[] memory) {
        SigningCoordinator.SigningCohort storage cohort = signingCohorts[cohortId];
        return cohort.chains;
    }

    function getProviders(uint32 cohortId) external view returns (address[] memory) {
        SigningCoordinator.SigningCohort storage cohort = signingCohorts[cohortId];
        address[] memory providers = new address[](cohort.signers.length);
        for (uint256 i = 0; i < cohort.signers.length; i++) {
            providers[i] = cohort.signers[i].provider;
        }
        return providers;
    }

    function initiateSigningCohort(
        uint256 chainId,
        address authority,
        address[] calldata providers,
        uint16 threshold,
        uint32 duration
    ) external returns (uint32) {
        SigningCoordinator.SigningCohort storage signingCohort = signingCohorts.push();

        signingCohort.initiator = msg.sender;
        signingCohort.authority = authority;
        signingCohort.numSigners = uint16(providers.length);
        signingCohort.threshold = threshold;
        signingCohort.initTimestamp = uint32(block.timestamp);
        signingCohort.endTimestamp = signingCohort.initTimestamp + duration;
        signingCohort.chains.push(chainId);

        for (uint256 i = 0; i < providers.length; i++) {
            address current = providers[i];
            SigningCoordinator.SigningCohortParticipant storage newParticipant = signingCohort
                .signers
                .push();
            newParticipant.provider = current;
        }
        uint32 id = uint32(signingCohorts.length - 1);
        cohortStates[id] = SigningCoordinator.SigningCohortState.AWAITING_SIGNATURES;

        return id;
    }

    function deployAdditionalChainForSigningMultisig(uint256 chainId, uint32 cohortId) external {
        SigningCoordinator.SigningCohort storage signingCohort = signingCohorts[cohortId];
        for (uint256 i = 0; i < signingCohort.chains.length; i++) {
            require(signingCohort.chains[i] != chainId, "Already deployed for this chain");
        }
        signingCohort.chains.push(chainId);
    }

    function extendSigningCohortDuration(uint32 cohortId, uint32 additionalDuration) external {
        SigningCoordinator.SigningCohort storage signingCohort = signingCohorts[cohortId];
        signingCohort.endTimestamp += additionalDuration;
    }
}
