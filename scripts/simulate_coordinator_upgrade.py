# Usage:
#  > ape run --interactive simulate_coordinator_upgrade --network polygon:mainnet-fork:foundry

from ape import accounts, chain, project

from deployment.constants import CONSTRUCTOR_PARAMS_DIR
from deployment.params import Deployer


OZ_DEPENDENCY = project.dependencies["openzeppelin"]["5.0.0"]
PROXY_ADMIN_ADDRESS = "0xeE711368eabA106A0cf7a07B33B84cD930331fFd"
COORDINATOR_PROXY_ADDRESS = "0xE74259e3dafe30bAA8700238e324b47aC98FE755"
CONSTRUCTOR_PARAMS_FILEPATH = CONSTRUCTOR_PARAMS_DIR / "mainnet" / "redeploy-coordinator.yml"
NUCO_MULTISIG_ADDRESS = "0x861aa915C785dEe04684444560fC7A2AB43a1543"


def main():
    nuco_multisig = accounts.test_accounts.impersonate_account(NUCO_MULTISIG_ADDRESS)
    chain.set_balance(nuco_multisig.address, "5 ether")

    proxy_admin = OZ_DEPENDENCY.ProxyAdmin.at(PROXY_ADMIN_ADDRESS)
    assert proxy_admin.owner() == nuco_multisig.address
    
    # Deploy new Coordinator implementation
    deployer = Deployer.from_yaml(filepath=CONSTRUCTOR_PARAMS_FILEPATH, verify=False, account=nuco_multisig, autosign=True)
    new_coordinator = deployer.deploy(project.Coordinator)

    # Upgrade Coordinator proxy to new implementation
    coordinator = project.Coordinator.at(COORDINATOR_PROXY_ADDRESS)
    tx = proxy_admin.upgradeAndCall(coordinator.address, new_coordinator, b"", sender=nuco_multisig)  

    print(f"Upgraded Coordinator to {new_coordinator.address} via ProxyAdmin {proxy_admin.address}")

    assert False, "Stop here"  # Force activation of interactive mode to inspect state after upgrade
