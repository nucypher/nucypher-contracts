#!/usr/bin/python3

from ape import project

from scripts.deployment import prepare_deployment
from scripts.registry import registry_from_ape_deployments
from scripts.constants import CONSTRUCTOR_PARAMS_DIR, ARTIFACTS_DIR

PUBLISH = False
CONSTRUCTOR_PARAMS_FILEPATH = CONSTRUCTOR_PARAMS_DIR / "lynx-alpha-13-params.json"
REGISTRY_FILEPATH = ARTIFACTS_DIR / "lynx-alpha-13-registry.json"


def main():
    """
    This script deploys the Lynx TACo Root Application,
    Lynx TACo Child Application, Lynx Ritual Token, and Lynx Coordinator.

    September 18, 2023, Goerli Deployment:
    ape run testnet deploy_lynx --network ethereum:goerli:<INFURA_URI>
    'LynxRootApplication' deployed to: 0x39F1061d68540F7eb57545C4C731E0945c167016
    'LynxTACoChildApplication' deployed to: 0x892a548592bA66dc3860F75d76cDDb488a838c35
    'Coordinator' deployed to: 0x18566d4590be23e4cb0a8476C80C22096C8c3418

    September 18, 2023, Mumbai Deployment:
     ape run testnet deploy_lynx --network polygon:mumbai:<INFURA_URI>
    'LynxRootApplication' deployed to: 0xb6400F55857716A3Ff863e6bE867F01F23C71793
    'LynxTACoChildApplication' deployed to: 0x3593f90b19F148FCbe7B00201f854d8839F33F86
    'Coordinator' deployed to: 0x4077ad1CFA834aEd68765dB0Cf3d14701a970a9a
    """

    deployer, params = prepare_deployment(
        params_filepath=CONSTRUCTOR_PARAMS_FILEPATH,
        registry_filepath=REGISTRY_FILEPATH,
        publish=PUBLISH
    )

    LynxRootApplication = deployer.deploy(
        *params.get(project.LynxRootApplication, locals()), **params.get_kwargs()
    )

    LynxTACoChildApplication = deployer.deploy(
        *params.get(project.LynxTACoChildApplication, locals()), **params.get_kwargs()
    )

    LynxRootApplication.setChildApplication(
        LynxTACoChildApplication.address,
        sender=deployer,
    )

    LynxRitualToken = deployer.deploy(
        *params.get(project.LynxRitualToken, locals()), **params.get_kwargs()
    )

    # Lynx Coordinator
    Coordinator = deployer.deploy(*params.get(project.Coordinator, locals()), **params.get_kwargs())

    LynxTACoChildApplication.setCoordinator(Coordinator.address, sender=deployer)

    GlobalAllowList = deployer.deploy(
        *params.get(project.GlobalAllowList, locals()), **params.get_kwargs()
    )

    deployments = [LynxRootApplication, LynxTACoChildApplication, LynxRitualToken, Coordinator, GlobalAllowList]

    registry_names = {
        LynxRootApplication.contract_type.name: "TACoApplication",
        LynxTACoChildApplication.contract_type.name: "TACoChildApplication",
    }

    output_filepath = registry_from_ape_deployments(
        deployments=deployments,
        registry_names=registry_names,
        output_filepath=REGISTRY_FILEPATH
    )
    print(f"(i) Registry written to {output_filepath}!")
