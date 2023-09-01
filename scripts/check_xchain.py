import time

from ape import accounts, networks, project


def main():
    deployer = accounts.load("TGoerli")
    print("*******")
    print("WARNING: This script will take 40 mins to run to allow messages to sync from L1 to L2")
    print("*******")
    with networks.ethereum.goerli.use_provider("infura"):
        root = project.PolygonRoot.at("0xD2Cb2A8fbE29adBa1C287b2A0b49f5C4fDc1f5BE")
        root.updateOperator(
            "0x3B42d26E19FF860bC4dEbB920DD8caA53F93c600",
            "0x3B42d26E19FF860bC4dEbB920DD8caA53F93c600",
            sender=deployer,
        )
    # check every 5 minutes
    print("Now: {}".format(time.time()))
    for i in range(12):
        time.sleep(60 * i * 5)
        print("Now: {}".format(time.time()))
        with networks.polygon.mumbai.use_provider("infura"):
            taco_child = project.TACoChildApplication.at(
                "0x68E95C2548363Bf5856667065Bc1B89CC498969F"
            )
            print(
                taco_child.stakingProviderFromOperator("0xAe87D865F3A507185656aD0ef52a8E0B9f3d58f8")
            )
            print(
                taco_child.stakingProviderFromOperator("0x3B42d26E19FF860bC4dEbB920DD8caA53F93c600")
            )
