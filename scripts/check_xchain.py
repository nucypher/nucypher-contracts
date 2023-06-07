import time

from ape import networks, project


def main():
    print("*******")
    print("WARNING: This script will take 40 mins to run to allow messages to sync from L1 to L2")
    print("*******")
    with networks.ethereum.goerli.use_provider("infura"):
        root = project.PolygonRoot.at("0xdc90A337DF9561705EB85B92391ab8F55d114D53")
        root.updateOperator(
            "0x3B42d26E19FF860bC4dEbB920DD8caA53F93c600",
            "0x3B42d26E19FF860bC4dEbB920DD8caA53F93c600",
        )
    time.sleep(60 * 40)
    with networks.polygon.mumbai.use_provider("infura"):
        stake_info = project.StakeInfo.at("0x40D0107ACa3503CB345E4117a9F92E8220EEEb3C")
        print(stake_info.operatorToProvider("0xAe87D865F3A507185656aD0ef52a8E0B9f3d58f8"))
        print(stake_info.operatorToProvider("0x3B42d26E19FF860bC4dEbB920DD8caA53F93c600"))
