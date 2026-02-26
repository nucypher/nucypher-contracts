#!/usr/bin/python3

import json

from ape import project, networks


SEEDNODES = [
    "0x97d065b567cc4543d20dffaa7009f9ade64d7e26",
    "0xc1268db05e7bd38bd85b2c3fef80f8968a2c933a",
]

TACO_CHILD_ADDRESS = "0xfa07aab78062fac4c36995bf28f6d677667973f5"
TACO_APP_ADDRESS = "0x347CC7ede7e5517bD47D20620B2CF1b406edcF07"
T_STAKING_ADDRESS = "0x01B67b1194C75264d06F808A921228a95C765dd7"

MIN_STAKE = 150_000 * 10**18

def t_tokens(x):
    return int(x / 10**18)


def main():
    # get provider from initially connected network
    provider_name = networks.active_provider.name

    # Retrieve TACoChildApplication data from Polygon
    with networks.polygon.mainnet.use_provider(provider_name):
        taco_child = project.TACoChildApplication.at(TACO_CHILD_ADDRESS)
        
        tokens_child, stakers_tokens_child = taco_child.getActiveStakingProviders(0, 200)
        print(f"Number of stakers in TACoChildApplication: {len(stakers_tokens_child)}")
        
        taco_child_data = {}
        for staker_token in stakers_tokens_child:
            staker, token = staker_token[:20], staker_token[20:]
            staker = staker.hex()
            token = int.from_bytes(token, byteorder="big")
            taco_child_data[staker] = token

    # Retrieve TACoApplication data from Ethereum
    with networks.ethereum.mainnet.use_provider(provider_name):
        taco_app = project.TACoApplication.at(TACO_APP_ADDRESS)
        
        tokens_app, stakers_tokens_app = taco_app.getActiveStakingProviders(0, 200, 0)
        print(f"Number of stakers in TACoApplication: {len(stakers_tokens_app)}")

        if len(stakers_tokens_child) != len(stakers_tokens_app):
            raise Exception("Number of stakers mismatch between child and app!")
        
        taco_app_data = {}
        for staker_token in stakers_tokens_app:
            staker, token = staker_token[:20], staker_token[20:]
            staker = staker.hex()
            token = int.from_bytes(token, byteorder="big")
            taco_app_data[staker] = token
    
    # Compare stakers and tokens between child and app
    for staker, token in taco_child_data.items():
        if staker in taco_app_data:
            if taco_app_data[staker] != token:
                print(f"Staker {staker}: Mismatched token value. Child: {token}, App: {taco_app_data[staker]}")
        else:
            print(f"Staker {staker}: Not found in app data")


    # Retrieve Threshold staking data:
    with networks.ethereum.mainnet.use_provider(provider_name):

        # Use Dune Analytics data for historical list of stakers in T staking
        # Data extracted with the following SQL query:
        #  `select distinct stakingProvider from threshold_network_ethereum.TokenStaking_evt_Staked`
        # See https://dune.com/queries/6738629
        with open("t_stakers_dune.json") as f:
            t_stakers = []
            dune_data = json.load(f)
            for row in dune_data["result"]["rows"]:
                t_staker = row["stakingProvider"]
                t_stakers.append(t_staker)

        print(f"Number of stakers in T staking: {len(t_stakers)}")

        # This test contract can be used since it has the same API as the real T staking contract
        t = project.TestnetThresholdStaking.at(T_STAKING_ADDRESS)

        total_authorized_stake = 0
        total_staked = 0
        total_staked_not_in_taco = 0

        beta_included = []
        beta_excluded = []
        released = []
        migrated = []

        # Analysis of T staking data
        t_stakes_data = {}
        for s in t_stakers:
            staked_amount = t.stakeAmount(s)
            t_stakes_data[s] = staked_amount

            if staked_amount == 0:
                # This is either:
                #  - a normal staker that already withdrew their stake, we can ignore them
                #  - a beta staker, which we analyze below
                continue
            
            total_staked += staked_amount

            if s not in taco_app_data:
                # This staker has tokens but not doing anything, so they should be released
                print(f"Staker {s}: Not found in taco app data. Staked amount: {t_tokens(staked_amount)} [RELEASED]")
                total_staked_not_in_taco += staked_amount
                released.append(s)

        print(f"Total staked in T staking: {t_tokens(total_staked)}")
        print(f"Total staked in T staking not in taco app: {t_tokens(total_staked_not_in_taco)}")
        print(f"Number of stakers in T staking not in taco app: {len(released)}")

        # Analysis of stakers in TACo app compared to T staking
        for s in taco_app_data:
            staked_amount = t_stakes_data[s]
            auth_amount = taco_app_data[s]

            total_authorized_stake += auth_amount

            if auth_amount < MIN_STAKE:
                # Release staker (low authorized stake)
                print(f"Staker {s}: Authorized stake is very low: {t_tokens(auth_amount)} [RELEASED]")
                released.append(s)
            elif auth_amount > staked_amount:
                # Beta stakers
                if s in SEEDNODES:
                    # Seednode --> Migrate
                    print(f"Staker {s}: Authorized >> staked: {t_tokens(auth_amount)} > {t_tokens(staked_amount)} [BETA INCLUDED]")
                    beta_included.append(s)
                    migrated.append(s)
                else:
                    # Non-seednode beta staker --> Release
                    print(f"Staker {s}: Authorized >> staked: {t_tokens(auth_amount)} > {t_tokens(staked_amount)} [BETA EXCLUDED]")
                    beta_excluded.append(s)
                    released.append(s)
            elif auth_amount < staked_amount:
                # Normal staker --> Migrate
                print(f"Staker {s}: Authorized << staked: {t_tokens(auth_amount)} < {t_tokens(staked_amount)}")
                migrated.append(s)
            else:
                # Normal staker --> Migrate
                print(f"Staker {s}: Authorized == staked: {t_tokens(auth_amount)}")
                migrated.append(s)
    
    # Final Summary
    print(f"Total authorized stake (includes wrong data from Beta stakers): {t_tokens(total_authorized_stake)}")
    print(f"Total staked: {t_tokens(total_staked)}")

    print(f"Number of migrated stakers: {len(migrated)}")
    print(f"\tNumber of normal stakers migrated: {len(migrated) - len(beta_included)}")
    print(f"\tNumber of beta stakers migrated: {len(beta_included)}")
    print(f"Number of released stakers: {len(released)}")
    print(f"\tNumber of beta stakers excluded: {len(beta_excluded)}")

    # List of addresses
    print(f"Beta stakers included: {beta_included}\n")
    print(f"Beta stakers excluded: {beta_excluded}\n")
    print(f"Migrated stakers: {migrated}\n")
    print(f"Released stakers: {released}")
 