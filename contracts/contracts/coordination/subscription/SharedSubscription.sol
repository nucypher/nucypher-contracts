// SPDX-License-Identifier: AGPL-3.0-or-later

pragma solidity ^0.8.0;

import "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import "@openzeppelin/contracts/token/ERC20/utils/SafeERC20.sol";
import "@openzeppelin-upgradeable/contracts/proxy/utils/Initializable.sol";
import "@openzeppelin-upgradeable/contracts/access/OwnableUpgradeable.sol";
import "./EncryptorSlotsSubscription.sol";
import "../IEncryptionAuthorizer.sol";
import "../IFeeModel.sol";

/**
 * @title SharedSubscription
 * @notice Manages the subscription information for rituals.
 */
contract SharedSubscription is IFeeModel, Initializable, OwnableUpgradeable {
    using SafeERC20 for IERC20;

    struct Billing {
        uint256 encryptorSlots;
        uint256 usedEncryptorSlots;
        uint256 endOfSubscription;
        uint256 encryptorFeeRate;
    }

    uint32 public constant INACTIVE_RITUAL_ID = type(uint32).max;

    Coordinator public immutable coordinator;
    IEncryptionAuthorizer public immutable accessController;
    IERC20 public immutable feeToken;

    address public immutable adopterSetter;

    uint256 public immutable encryptorFeeRate;

    uint256[3][10] public feePackages;
    uint32 public activeRitualId;
    mapping(address authAdmin => Billing billingInfo) public billing;
    address public adopter;

    uint256[20] private gap;

    /**
     * @notice Emitted when a subscription is spent
     * @param treasury The address of the treasury
     * @param amount The amount withdrawn
     */
    event WithdrawalToTreasury(address indexed treasury, uint256 amount);

    /**
     * @notice Emitted when a subscription is paid
     * @param subscriber The address of the subscriber
     * @param authAdmin Autharization admin that was paid
     * @param amount The amount paid
     * @param encryptorSlots Number of encryptor slots
     * @param endOfSubscription End timestamp of subscription
     */
    event SubscriptionPaid(
        address indexed subscriber,
        address indexed authAdmin,
        uint256 amount,
        uint256 encryptorSlots,
        uint256 endOfSubscription
    );

    /**
     * @notice Sets the coordinator and fee token contracts
     * @dev The coordinator and fee token contracts cannot be zero addresses
     * @param _coordinator The address of the coordinator contract
     * @param _accessController The address of the global allow list
     * @param _feeToken The address of the fee token contract
     * @param _adopterSetter Address that can set the adopter address
     * @param _feePackages Fee packages [duration(sec), encryptors, feeRate]
     */
    constructor(
        Coordinator _coordinator,
        IEncryptionAuthorizer _accessController,
        IERC20 _feeToken,
        address _adopterSetter,
        uint256[3][10] memory _feePackages
    ) {
        require(address(_feeToken) != address(0), "Fee token cannot be the zero address");
        require(_adopterSetter != address(0), "Adopter setter cannot be the zero address");
        require(
            address(_accessController) != address(0),
            "Access controller cannot be the zero address"
        );
        require(address(_coordinator) != address(0), "Coordinator cannot be the zero address");
        coordinator = _coordinator;
        feeToken = _feeToken;
        adopterSetter = _adopterSetter;
        accessController = _accessController;
        feePackages = _feePackages;
        _disableInitializers();
    }

    modifier onlyAccessController() {
        require(
            msg.sender == address(accessController),
            "Only Access Controller can call this method"
        );
        _;
    }

    modifier onlyActiveRitual(uint32 ritualId) {
        require(
            activeRitualId != INACTIVE_RITUAL_ID && ritualId == activeRitualId,
            "Ritual must be active"
        );
        _;
    }

    modifier onlyCoordinator() {
        require(msg.sender == address(coordinator), "Only the Coordinator can call this method");
        _;
    }

    /**
     * @notice Initialize function for using with OpenZeppelin proxy
     */
    function initialize(address _treasury) external initializer {
        activeRitualId = INACTIVE_RITUAL_ID;
        __Ownable_init(_treasury);
    }

    function setAdopter(address _adopter) external {
        require(msg.sender == adopterSetter, "Only adopter setter can set adopter");
        require(
            adopter == address(0) && _adopter != address(0),
            "Adopter can be set only once with not zero address"
        );
        adopter = _adopter;
    }

    function getEncryptorFeeRate(
        uint256 encryptorSlots,
        uint256 duration
    ) public view returns (uint256) {
        for (uint256 i = 0; i < feePackages.length; i++) {
            uint256[3] storage feePackage = feePackages[i];
            if (feePackage[0] == duration && feePackage[1] == encryptorSlots) {
                return feePackage[2];
            }
        }
        revert("Fee package is not available");
    }

    function encryptorFees(
        uint256 encryptorFeeRate,
        uint256 encryptorSlots,
        uint256 duration
    ) public view returns (uint256) {
        return encryptorFeeRate * duration * encryptorSlots;
    }

    /**
     * @notice Process payment for the chosen package
     * @param authAdmin Address of the admin
     * @param encryptorSlots Number of encryptor slots
     * @param packageDuration Requested duration
     */
    function payForSubscription(
        address authAdmin,
        uint256 encryptorSlots,
        uint256 packageDuration
    ) external returns (uint256 fees) {
        Billing storage billingInfo = billing[authAdmin];
        require(
            billingInfo.endOfSubscription < block.timestamp + packageDuration,
            "Renewal allowed only to later end of subscription"
        );

        uint256 discount = 0;
        if (billingInfo.endOfSubscription > block.timestamp) {
            uint256 restOfSubscription = billingInfo.endOfSubscription - block.timestamp;
            discount = encryptorFees(
                billingInfo.encryptorFeeRate,
                billingInfo.encryptorSlots,
                restOfSubscription
            );
        }

        billingInfo.encryptorSlots = encryptorSlots;
        billingInfo.endOfSubscription = block.timestamp + packageDuration;
        billingInfo.encryptorFeeRate = getEncryptorFeeRate(encryptorSlots, packageDuration);

        fees =
            encryptorFees(billingInfo.encryptorFeeRate, encryptorSlots, packageDuration) -
            discount;
        emit SubscriptionPaid(
            msg.sender,
            authAdmin,
            fees,
            billingInfo.encryptorSlots,
            billingInfo.endOfSubscription
        );
        feeToken.safeTransferFrom(msg.sender, address(this), fees);
    }

    /**
     * @notice Withdraws the fees to the treasury
     */
    function withdrawToTreasury() external {
        uint256 amount = feeToken.balanceOf(address(this));
        require(0 < amount, "Insufficient balance available");
        feeToken.safeTransfer(owner(), amount);
        emit WithdrawalToTreasury(owner(), amount);
    }

    function processRitualPayment(
        address initiator,
        uint32 ritualId,
        uint256,
        uint32
    ) external onlyCoordinator {
        require(initiator == adopter, "Only adopter can initiate ritual");
        require(
            address(accessController) != address(0) &&
                accessController == coordinator.getAccessController(ritualId),
            "Access controller for ritual must be approved"
        );

        if (activeRitualId != INACTIVE_RITUAL_ID) {
            Coordinator.RitualState state = coordinator.getRitualState(activeRitualId);
            require(
                state == Coordinator.RitualState.DKG_INVALID ||
                    state == Coordinator.RitualState.DKG_TIMEOUT ||
                    state == Coordinator.RitualState.EXPIRED, // TODO check if it's ok
                "Only failed/expired rituals allowed to be reinitiated"
            );
        }
        activeRitualId = ritualId;
    }

    function beforeSetAuthorization(
        address authAdmin,
        uint32,
        address[] calldata addresses,
        bool value
    ) public virtual {
        Billing storage billingInfo = billing[authAdmin];
        require(block.timestamp <= billingInfo.endOfSubscription, "Subscription has expired");
        if (value) {
            billingInfo.usedEncryptorSlots += addresses.length;
            require(
                billingInfo.usedEncryptorSlots <= billingInfo.encryptorSlots,
                "Encryptors slots filled up"
            );
        } else {
            if (billingInfo.usedEncryptorSlots >= addresses.length) {
                billingInfo.usedEncryptorSlots -= addresses.length;
            } else {
                billingInfo.usedEncryptorSlots = 0;
            }
        }
    }

    function beforeIsAuthorized(address authAdmin, uint32) public view virtual {
        Billing storage billingInfo = billing[authAdmin];
        require(block.timestamp <= billingInfo.endOfSubscription, "Subscription has expired");
        // used encryptor slots must be paid
        require(
            billingInfo.usedEncryptorSlots <= billingInfo.encryptorSlots,
            "Encryptors slots filled up"
        );
    }

    /**
     * @dev This function is called before the setAuthorizations function
     */
    function beforeSetAuthorization(uint32, address[] calldata, bool) public virtual override {
        revert("Unused");
    }

    /**
     * @dev This function is called before the isAuthorized function
     */
    function beforeIsAuthorized(uint32) public view virtual override {
        revert("Unused");
    }

    function processRitualExtending(
        address initiator,
        uint32 ritualId,
        uint256,
        uint32
    ) external view override onlyCoordinator onlyActiveRitual(ritualId) {
        require(initiator == adopter, "Only adopter can extend ritual");
    }
}
