# NuCypher contracts

Contracts from the [main NuCypher codebase](https://github.com/nucypher/nucypher) extracted into a separate repo for ease of testing and interoperability with other projects.

## Structure

* `artifacts`: ABI and address of deployed contracts
* `contracts`: Source code for contracts
* `scripts`: Deployment scripts
* `tests`: Contract tests

## Installation

We use [Brownie](https://eth-brownie.readthedocs.io/) as the testing and deployment framework of this project.

### Configuring Pre-commit

To install pre-commit locally:

```bash
pre-commit install
```

### Github Actions envvars

In future, we may need to set the following:

* `ETHERSCAN_TOKEN`: Etherscan [API token](https://etherscan.io/apis), required to query source files from Etherscan.
* `GITHUB_TOKEN`: Github [personal access token](https://help.github.com/en/github/authenticating-to-github/creating-a-personal-access-token-for-the-command-line#creating-a-token), required by [py-solc-x](https://github.com/iamdefinitelyahuman/py-solc-x) when querying installable solc versions.
* `WEB3_INFURA_PROJECT_ID`: Infura [project ID](https://eth-brownie.readthedocs.io/en/latest/nonlocal-networks.html#using-infura), required for connecting to Infura hosted nodes.

## Running the Tests

This project uses [tox](https://tox.readthedocs.io/en/latest/) to standardize the local and remote testing environments.
Note that `tox` will install the dependencies from `requirements.txt` automatically and run a linter (`black`); if that is not desirable, you can just run `py.test`.

## Deploy to Production and Test
In order to deploy to **production** you will need to have configured brownie with the mainnet account you wish to use:
```
$ brownie accounts new <id>
```
You will be asked to input the private key, and to choose a password. The account will then be available as `<id>`.

Then run the deployment scripts:
```
$ brownie run scripts/deploy_subscription_manager.py main <id> --network polygon-main
$ brownie run scripts/deploy_staking_escrow.py main <id> --network rinkeby
```

Configurations for the deployments are in `brownie-config.yaml`.
For example, `StakingEscrow.sol` requires Nu token Contract, T Staking Contract, and Worklock Contract.
These are defined by:
```
  mainnet:
    nu_token: '0x4fE83213D56308330EC302a8BD641f1d0113A4Cc'
    t_staking: '0x01B67b1194C75264d06F808A921228a95C765dd7'
    work_lock: '0xe9778E69a961e64d3cdBB34CF6778281d34667c2'
```


To deploy to a local ganache development environment:
```
$ brownie run scripts/deploy_subscription_manager.py --network development
```

The networks used here are standard brownie networks, you can see the full list with:
```
$ brownie networks list
```