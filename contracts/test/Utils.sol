// SPDX-License-Identifier: AGPL-3.0-or-later

pragma solidity ^0.8.0;


import "@openzeppelin/contracts/proxy/transparent/ProxyAdmin.sol";
import "@openzeppelin/contracts/proxy/transparent/TransparentUpgradeableProxy.sol";


// Ext contracts used to compile dependencies
contract ProxyAdminExt is ProxyAdmin {

}

contract TransparentUpgradeableProxyExt is TransparentUpgradeableProxy {

    constructor(
        address _logic,
        address admin_,
        bytes memory _data
    ) TransparentUpgradeableProxy(_logic, admin_, _data) {

    }

}
