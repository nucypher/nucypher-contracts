// SPDX-License-Identifier: AGPL-3.0-or-later

pragma solidity ^0.8.0;


import "../aragon/interfaces/IERC900History.sol";
import "./NuCypherToken.sol";
import "./lib/Bits.sol";
import "./proxy/Upgradeable.sol";
import "@openzeppelin/contracts/utils/math/Math.sol";
import "@openzeppelin/contracts/token/ERC20/utils/SafeERC20.sol";
import "@threshold/contracts/staking/IStaking.sol";


/**
* @notice WorkLock interface
*/
interface WorkLockInterface {
    function token() external view returns (NuCypherToken);
}


/**
* @notice VendingMachine interface
*/
interface IVendingMachine {

    function wrappedToken() external returns (IERC20);
    function tToken() external returns (IERC20);
    function wrap(uint256 amount) external;
    function unwrap(uint256 amount) external;
    function conversionToT(uint256 amount) external view returns (uint256 tAmount, uint256 wrappedRemainder);
    function conversionFromT(uint256 amount) external view returns (uint256 wrappedAmount, uint256 tRemainder);
    
}


/**
* @title StakingEscrow
* @notice Contract holds and locks stakers tokens.
* Each staker that locks their tokens will receive some compensation
* @dev |v6.2.3|
*/
contract StakingEscrow is Upgradeable, IERC900History {

    using Bits for uint256;
    using SafeERC20 for NuCypherToken;

    /**
    * @notice Signals that tokens were deposited
    * @param staker Staker address
    * @param value Amount deposited (in NuNits)
    */
    event Deposited(address indexed staker, uint256 value);

    /**
    * @notice Signals that NU tokens were withdrawn to the staker
    * @param staker Staker address
    * @param value Amount withdraws (in NuNits)
    */
    event Withdrawn(address indexed staker, uint256 value);

    /**
    * @notice Signals that the staker was slashed
    * @param staker Staker address
    * @param penalty Slashing penalty
    * @param investigator Investigator address
    * @param reward Value of reward provided to investigator (in NuNits)
    */
    event Slashed(address indexed staker, uint256 penalty, address indexed investigator, uint256 reward);

    /**
    * @notice Signals that vesting parameters were set for the staker
    * @param staker Staker address
    * @param releaseTimestamp Release timestamp
    * @param releaseRate Release rate
    */
    event VestingSet(address indexed staker, uint256 releaseTimestamp, uint256 releaseRate);

    /**
    * @notice Signals that the staker requested merge with T staking contract
    * @param staker Staker address
    * @param stakingProvider Staking provider address
    */
    event MergeRequested(address indexed staker, address indexed stakingProvider);
    
    /**
    * @notice Signals that NU tokens were wrapped and topped up to the existing T stake
    * @param staker Staker address
    * @param value Amount wrapped (in NuNits)
    */
    event WrappedAndToppedUp(address indexed staker, uint256 value);

    struct StakerInfo {
        uint256 value;

        uint16 stub1; // former slot for currentCommittedPeriod // TODO combine slots?
        uint16 stub2; // former slot for nextCommittedPeriod
        uint16 lastCommittedPeriod; // used only in depositFromWorkLock
        uint16 stub4; // former slot for lockReStakeUntilPeriod
        uint256 stub5; // former slot for completedWork
        uint16 stub6; // former slot for workerStartPeriod
        address stub7; // former slot for worker

        uint256 flags; // uint256 to acquire whole slot and minimize operations on it

        uint256 vestingReleaseTimestamp;
        uint256 vestingReleaseRate;
        address stakingProvider;

        uint256 reservedSlot4;
        uint256 reservedSlot5;

        uint256[] stub8; // former slot for pastDowntime
        uint256[] stub9; // former slot for subStakes
        uint128[] stub10; // former slot for history

    }

    // indices for flags (0-4 were in use, skip it in future)
//    uint8 internal constant SOME_FLAG_INDEX = 5;

    NuCypherToken public immutable token;
    WorkLockInterface public immutable workLock;
    IStaking public immutable tStaking;
    IERC20 public immutable tToken;
    IVendingMachine public immutable vendingMachine;

    uint128 private stub1; // former slot for previousPeriodSupply
    uint128 public currentPeriodSupply; // resulting token supply
    uint16 private stub2; // former slot for currentMintingPeriod

    mapping (address => StakerInfo) public stakerInfo;
    address[] public stakers;
    mapping (address => address) private stub3; // former slot for stakerFromWorker

    mapping (uint16 => uint256) private stub4; // former slot for lockedPerPeriod
    uint128[] private stub5;  // former slot for balanceHistory

    address private stub6; // former slot for PolicyManager
    address private stub7; // former slot for Adjudicator
    address private stub8; // former slot for WorkLock

    mapping (uint16 => uint256) private stub9; // last former slot for lockedPerPeriod

    /**
    * @notice Constructor sets address of token contract and parameters for staking
    * @param _token NuCypher token contract
    * @param _workLock WorkLock contract. Zero address if there is no WorkLock
    * @param _tStaking T token staking contract
    * @param _vendingMachine Nu vending machine
    */
    constructor(
        NuCypherToken _token,
        WorkLockInterface _workLock,
        IStaking _tStaking,
        IERC20 _tToken,
        IVendingMachine _vendingMachine
    ) {
        require(_token.totalSupply() > 0 &&
            _tStaking.getApplicationsLength() != 0 &&
            (address(_workLock) == address(0) || _workLock.token() == _token) &&
            _vendingMachine.wrappedToken() == _token &&
            _vendingMachine.tToken() == _tToken,
            "Input addresses must be deployed contracts"
        );

        token = _token;
        workLock = _workLock;
        tStaking = _tStaking;
        tToken = _tToken;
        vendingMachine = _vendingMachine;
    }

    /**
    * @dev Checks the existence of a staker in the contract
    */
    modifier onlyStaker()
    {
        require(stakerInfo[msg.sender].value > 0, "Caller must be a staker");
        _;
    }

    /**
    * @dev Checks caller is T staking contract
    */
    modifier onlyTStakingContract()
    {
        require(msg.sender == address(tStaking), "Caller must be the T staking contract");
        _;
    }

    /**
    * @dev Checks caller is WorkLock contract
    */
    modifier onlyWorkLock()
    {
        require(msg.sender == address(workLock), "Caller must be the WorkLock contract");
        _;
    }

    //------------------------Main getters------------------------
    /**
    * @notice Get all tokens belonging to the staker
    */
    function getAllTokens(address _staker) external view returns (uint256) {
        return stakerInfo[_staker].value;
    }

    /**
    * @notice Get work that completed by the staker
    */
    function getCompletedWork(address _staker) external view returns (uint256) {
        return token.totalSupply();
    }


    //------------------------Main methods------------------------
    /**
    * @notice Stub for WorkLock
    * @param _staker Staker
    * @param _measureWork Value for `measureWork` parameter
    * @return Work that was previously done
    */
    function setWorkMeasurement(address _staker, bool _measureWork)
        external onlyWorkLock returns (uint256)
    {
        return 0;
    }

    /**
    * @notice Deposit tokens from WorkLock contract
    * @param _staker Staker address
    * @param _value Amount of tokens to deposit
    * @param _unlockingDuration Amount of periods during which tokens will be unlocked when wind down is enabled
    */
    function depositFromWorkLock(
        address _staker,
        uint256 _value,
        uint16 _unlockingDuration
    )
        external onlyWorkLock
    {
        require(_value != 0, "Amount of tokens to deposit must be specified");
        StakerInfo storage info = stakerInfo[_staker];
        // initial stake of the staker
        if (info.value == 0 && info.lastCommittedPeriod == 0) {
            stakers.push(_staker);
        }
        token.safeTransferFrom(msg.sender, address(this), _value);
        info.value += _value;

        emit Deposited(_staker, _value);
    }

    /**
    * @notice Withdraw available amount of NU tokens to staker
    * @param _value Amount of tokens to withdraw
    */
    function withdraw(uint256 _value) external onlyStaker {
        require(_value > 0, "Value must be specified");
        StakerInfo storage info = stakerInfo[msg.sender];
        require(
            _value <= info.value,
            "Not enough tokens"
        );
        info.value -= _value;

        token.safeTransfer(msg.sender, _value);
        emit Withdrawn(msg.sender, _value);
    }

    /**
    * @notice Wraps all tokens and top up stake in T staking contract
    */
    function wrapAndTopUp() external onlyStaker {
        StakerInfo storage info = stakerInfo[msg.sender];
        require(info.stakingProvider != address(0), "There is no stake in T staking contract");

        (uint256 tTokenAmount, uint256 remainder) = vendingMachine.conversionToT(
            info.value
        );

        uint256 wrappedTokenAmount = info.value - remainder;
        token.approve(address(vendingMachine), wrappedTokenAmount);
        vendingMachine.wrap(wrappedTokenAmount);
        tToken.approve(address(tStaking), tTokenAmount);
        tStaking.topUp(info.stakingProvider, uint96(tTokenAmount));
        info.value = remainder;
        emit WrappedAndToppedUp(msg.sender, wrappedTokenAmount);
    }

    //-------------Additional getters for stakers info-------------
    /**
    * @notice Return the length of the array of stakers
    */
    function getStakersLength() external view virtual returns (uint256) {
        return stakers.length;
    }

    //------------------ ERC900 connectors ----------------------

    function totalStakedForAt(address _owner, uint256 _blockNumber) public view override returns (uint256) {
        return 0;
    }

    function totalStakedAt(uint256 _blockNumber) public view override returns (uint256) {
        return token.totalSupply();
    }

    function supportsHistory() external pure override returns (bool) {
        return true;
    }

    //------------------------Upgradeable------------------------
    /**
    * @dev Get StakerInfo structure by delegatecall
    */
    function delegateGetStakerInfo(address _target, bytes32 _staker)
        internal returns (StakerInfo memory result)
    {
        bytes32 memoryAddress = delegateGetData(_target, this.stakerInfo.selector, 1, _staker, 0);
        assembly {
            result := memoryAddress
        }
    }

    /// @dev the `onlyWhileUpgrading` modifier works through a call to the parent `verifyState`
    function verifyState(address _testTarget) public override virtual {
        super.verifyState(_testTarget);

        require(delegateGet(_testTarget, this.getStakersLength.selector) == stakers.length);
        if (stakers.length == 0) {
            return;
        }
        address stakerAddress = stakers[0];
        require(address(uint160(delegateGet(_testTarget, this.stakers.selector, 0))) == stakerAddress);
        StakerInfo storage info = stakerInfo[stakerAddress];
        bytes32 staker = bytes32(uint256(uint160(stakerAddress)));
        StakerInfo memory infoToCheck = delegateGetStakerInfo(_testTarget, staker);
        require(infoToCheck.value == info.value &&
            infoToCheck.vestingReleaseTimestamp == info.vestingReleaseTimestamp &&
            infoToCheck.vestingReleaseRate == info.vestingReleaseRate &&
            infoToCheck.stakingProvider == info.stakingProvider &&
            infoToCheck.flags == info.flags
        );
    }

}
