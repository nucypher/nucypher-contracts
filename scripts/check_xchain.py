from ape import project


def main():
    stake_info = project.StakeInfo.at("0x40D0107ACa3503CB345E4117a9F92E8220EEEb3C")
    print(stake_info.operatorToProvider("0xAe87D865F3A507185656aD0ef52a8E0B9f3d58f8"))
    print(stake_info.operatorToProvider("0x3B42d26E19FF860bC4dEbB920DD8caA53F93c600"))
