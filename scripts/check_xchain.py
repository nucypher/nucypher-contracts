import time

from ape import accounts, networks, project


def main():
    deployer = accounts.load("TGoerli")
    print("*******")
    print("WARNING: This script will take 40 mins to run to allow messages to sync from L1 to L2")
    print("*******")
    with networks.ethereum.goerli.use_provider("infura"):
        root = project.PolygonRoot.at("0x55D1E362b81FDC6BaA359630bf3Ffa5900F66777")
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
            stake_info = project.StakeInfo.at("0x96e7dBa88f79e5CCAEBf0c7678539F6C0d719c99")
            print(
                stake_info.stakingProviderFromOperator("0xAe87D865F3A507185656aD0ef52a8E0B9f3d58f8")
            )
            print(
                stake_info.stakingProviderFromOperator("0x3B42d26E19FF860bC4dEbB920DD8caA53F93c600")
            )
