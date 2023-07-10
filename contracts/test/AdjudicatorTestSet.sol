// SPDX-License-Identifier: AGPL-3.0-or-later

pragma solidity ^0.8.0;


import "../contracts/Adjudicator.sol";
import "../contracts/lib/SignatureVerifier.sol";
//import "../contracts/proxy/Upgradeable.sol";


/**
* @notice Contract for testing the Adjudicator contract
*/
contract PRECBDApplicationForAdjudicatorMock {

    uint32 public immutable secondsPerPeriod = 1;
    mapping (address => uint96) public stakingProviderInfo;
    mapping (address => uint256) public rewardInfo;
    mapping (address => address) _stakingProviderFromOperator;

    function stakingProviderFromOperator(address _operator) public view returns (address) {
        return _stakingProviderFromOperator[_operator];
    }

    function setStakingProviderInfo(address _stakingProvider, uint96 _amount, address _operator) public {
        stakingProviderInfo[_stakingProvider] = _amount;
        if (_operator == address(0)) {
            _operator = _stakingProvider;
        }
        _stakingProviderFromOperator[_operator] = _stakingProvider;
    }

    function authorizedStake(address _stakingProvider) public view returns (uint96) {
        return stakingProviderInfo[_stakingProvider];
    }

    function slash(
        address _stakingProvider,
        uint96 _penalty,
        address _investigator
    )
        external
    {
        stakingProviderInfo[_stakingProvider] -= _penalty;
        rewardInfo[_investigator] += 1;
    }

}


///**
//* @notice Upgrade to this contract must lead to fail
//*/
//contract AdjudicatorBad is Upgradeable {
//
//    mapping (bytes32 => bool) public evaluatedCFrags;
//    mapping (address => uint256) public penaltyHistory;
//
//}
//
//
///**
//* @notice Contract for testing upgrading the Adjudicator contract
//*/
//contract AdjudicatorV2Mock is Adjudicator {
//
//    uint256 public valueToCheck;
//
//    constructor(
//        SignatureVerifier.HashAlgorithm _hashAlgorithm,
//        uint256 _basePenalty,
//        uint256 _percentagePenalty,
//        uint256 _penaltyHistoryCoefficient
//    )
//        Adjudicator(
//            _hashAlgorithm,
//            _basePenalty,
//            _percentagePenalty,
//            _penaltyHistoryCoefficient
//        )
//    {
//    }
//
//    function setValueToCheck(uint256 _valueToCheck) public {
//        valueToCheck = _valueToCheck;
//    }
//
//    function verifyState(address _testTarget) override public {
//        super.verifyState(_testTarget);
//        require(uint256(delegateGet(_testTarget, this.valueToCheck.selector)) == valueToCheck);
//    }
//}
