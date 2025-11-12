import os

import ape
import pytest
from eth_utils import to_checksum_address

NUM_SIGNERS = 5
THRESHOLD = 2


@pytest.fixture(scope="module")
def signers(accounts):
    _accounts = [acc.address for acc in accounts[:NUM_SIGNERS]]
    return _accounts


@pytest.fixture(scope="module")
def deployer(accounts):
    deployer = accounts[NUM_SIGNERS + 1]
    return deployer


@pytest.fixture(scope="module")
def allowed_caller(accounts):
    return accounts[NUM_SIGNERS + 2]


@pytest.fixture(scope="module")
def unauthorized_caller(accounts):
    return accounts[NUM_SIGNERS + 3]


@pytest.fixture()
def signing_coordinator_child(
    project, oz_dependency, deployer, allowed_caller, threshold_signing_multisig_impl
):
    contract = project.SigningCoordinatorChild.deploy(
        sender=deployer,
    )
    proxy = oz_dependency.TransparentUpgradeableProxy.deploy(
        contract.address,
        deployer,
        b"",
        sender=deployer,
    )
    proxy_contract = project.SigningCoordinatorChild.at(proxy.address)

    signing_factory_contract = project.ThresholdSigningMultisigCloneFactory.deploy(
        threshold_signing_multisig_impl.address,
        proxy_contract.address,
        sender=deployer,
    )

    proxy_contract.initialize(signing_factory_contract.address, allowed_caller, sender=deployer)
    assert proxy_contract.allowedCaller() == allowed_caller.address
    assert proxy_contract.signingMultisigFactory() == signing_factory_contract.address
    assert proxy_contract.owner() == deployer.address

    return proxy_contract


@pytest.fixture(scope="module")
def threshold_signing_multisig_impl(project, deployer):
    threshold_signing_multisig_impl = project.ThresholdSigningMultisig.deploy(
        sender=deployer,
    )
    return threshold_signing_multisig_impl


def test_set_multisig_factory(
    project,
    deployer,
    allowed_caller,
    unauthorized_caller,
    signing_coordinator_child,
    threshold_signing_multisig_impl,
):
    new_factory_contract = project.ThresholdSigningMultisigCloneFactory.deploy(
        threshold_signing_multisig_impl.address,
        signing_coordinator_child.address,
        sender=deployer,
    )

    # must be owner
    with ape.reverts(f"account={unauthorized_caller.address}"):
        signing_coordinator_child.setMultisigFactory(
            new_factory_contract.address, sender=unauthorized_caller
        )

    with ape.reverts(f"account={allowed_caller.address}"):
        signing_coordinator_child.setMultisigFactory(
            new_factory_contract.address, sender=allowed_caller
        )

    signing_coordinator_child.setMultisigFactory(new_factory_contract.address, sender=deployer)
    assert signing_coordinator_child.signingMultisigFactory() == new_factory_contract.address


def test_set_allowed_caller(
    deployer, allowed_caller, unauthorized_caller, signing_coordinator_child
):
    # must be owner
    with ape.reverts(f"account={unauthorized_caller.address}"):
        signing_coordinator_child.setAllowedCaller(
            unauthorized_caller.address, sender=unauthorized_caller
        )

    with ape.reverts(f"account={allowed_caller.address}"):
        signing_coordinator_child.setAllowedCaller(allowed_caller.address, sender=allowed_caller)

    assert signing_coordinator_child.owner() == deployer.address
    signing_coordinator_child.setAllowedCaller(unauthorized_caller.address, sender=deployer)
    assert signing_coordinator_child.allowedCaller() == unauthorized_caller.address


def test_deploy_cohort_multisig(
    project, deployer, allowed_caller, signers, signing_coordinator_child
):
    cohort_id = 42

    # must be allowed caller
    with ape.reverts("Unauthorized caller"):
        signing_coordinator_child.deployCohortMultiSig(
            cohort_id, signers, THRESHOLD, sender=deployer
        )

    signing_coordinator_child.deployCohortMultiSig(
        cohort_id, signers, THRESHOLD, sender=allowed_caller
    )
    cohort_42_multisig_address = signing_coordinator_child.cohortMultisigs(cohort_id)
    cohort_42_multisig_contract = project.ThresholdSigningMultisig.at(cohort_42_multisig_address)
    assert cohort_42_multisig_contract.getSigners() == signers
    assert cohort_42_multisig_contract.threshold() == THRESHOLD

    # deploying again for the same cohort should fail
    with ape.reverts("Multisig already deployed"):
        signing_coordinator_child.deployCohortMultiSig(
            cohort_id, signers, THRESHOLD, sender=allowed_caller
        )

    # deploy for other cohort
    other_cohort_id = 43
    cohort_43_threshold = 1
    cohort_43_signers = [
        to_checksum_address(os.urandom(20)) for _ in range(cohort_43_threshold + 1)
    ]
    signing_coordinator_child.deployCohortMultiSig(
        other_cohort_id, cohort_43_signers, cohort_43_threshold, sender=allowed_caller
    )
    cohort_43_multisig_address = signing_coordinator_child.cohortMultisigs(other_cohort_id)
    # different address from 1st one
    assert cohort_43_multisig_address != cohort_42_multisig_address

    cohort_43_multisig_contract = project.ThresholdSigningMultisig.at(cohort_43_multisig_address)
    assert cohort_43_multisig_contract.getSigners() == cohort_43_signers
    assert cohort_43_multisig_contract.threshold() == cohort_43_threshold


def test_update_multisig_parameters(
    project, deployer, allowed_caller, unauthorized_caller, signers, signing_coordinator_child
):
    cohort_id = 100
    signing_coordinator_child.deployCohortMultiSig(
        cohort_id, signers, THRESHOLD, sender=allowed_caller
    )
    cohort_multisig_address = signing_coordinator_child.cohortMultisigs(cohort_id)
    cohort_multisig_contract = project.ThresholdSigningMultisig.at(cohort_multisig_address)

    new_threshold = 3
    new_signers = [to_checksum_address(os.urandom(20)) for _ in range(NUM_SIGNERS + 2)]

    # must be allowed caller
    with ape.reverts("Unauthorized caller"):
        signing_coordinator_child.updateMultiSigParameters(
            cohort_id, signers, new_threshold, True, sender=deployer
        )

    # must have already been deployed
    with ape.reverts("Multisig not deployed"):
        signing_coordinator_child.updateMultiSigParameters(
            11, signers, new_threshold, True, sender=allowed_caller
        )

    # don't replace, bulk add and update
    signing_coordinator_child.updateMultiSigParameters(
        cohort_id, new_signers, new_threshold, False, sender=allowed_caller
    )
    assert cohort_multisig_contract.threshold() == new_threshold
    assert len(cohort_multisig_contract.getSigners()) == len(signers) + len(new_signers)
    assert set(cohort_multisig_contract.getSigners()) == set(signers).union(set(new_signers))

    # totally replace
    signing_coordinator_child.updateMultiSigParameters(
        cohort_id, new_signers, new_threshold, True, sender=allowed_caller
    )
    assert cohort_multisig_contract.threshold() == new_threshold
    assert cohort_multisig_contract.getSigners() == new_signers
