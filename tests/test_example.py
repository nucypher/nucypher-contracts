

# Just a dummy test to give the system something to run
def test_example(project, accounts):
    # Before execution, the contract needs to be deployed
    project.ReEncryptionValidator.deploy(sender=accounts[0])

    # Then it can be called as:
    # ReEncryptionValidator[0].validateCFrag(capsule_bytes, cfrag_bytes, precomputed_data)
