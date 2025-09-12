# NuCypher contracts

Contracts from the [main NuCypher codebase](https://github.com/nucypher/nucypher) extracted into a separate repo for ease of testing and interoperability with other projects.

## Structure

* `deployment`: Deployment utilities
* `deployment/artifacts`: ABI and address of deployed contracts
* `contracts`: Source code for contracts
* `scripts`: Deployment and utilities scripts
* `tests`: Contract tests
* `src`: NPM package sources

## Installation

We use [Ape](https://docs.apeworx.io/ape/stable/index.html) as the testing and deployment framework of this project.

### Configuring Pre-commit

To install pre-commit locally:

```bash
pre-commit install
```

### Github Actions envvars

In future, we may need to set the following:

* `ETHERSCAN_API_KEY`: Etherscan [API token](https://etherscan.io/apis), required to query source files from Etherscan.
* `POLYGONSCAN_API_KEY`: Polygonscan [API token](https://polygonscan.com/apis), required to query source files from Polygonscan.
* `GITHUB_TOKEN`: Github [personal access token](https://help.github.com/en/github/authenticating-to-github/creating-a-personal-access-token-for-the-command-line#creating-a-token), required by [py-solc-x](https://github.com/iamdefinitelyahuman/py-solc-x) when querying installable solc versions.
* `WEB3_INFURA_PROJECT_ID`: Infura project ID, required for connecting to Infura hosted nodes.

## Running the Tests

### Python Tests

This project uses [tox](https://tox.readthedocs.io/en/latest/) to standardize the local and remote testing environments.
Note that `tox` will install the dependencies from `requirements.txt` automatically and run a linter (`black`); if that is not desirable, you can just run `py.test`.

### TypeScript Tests

To run the TypeScript tests, you will need to install the dependencies:

```bash
$ npm install
```

Then you can run the tests:

```bash
$ npm test
```

## Deploy to Production

### 1. Setup Deployment Parameters

Configurations for the deployments are in `deployments/constructor_params/<domain>/<filename>.yaml`.

Here is an example deployment configuration YAML file, but you can also find a full
examples in `deployments/constructor_params/lynx/`:

```yaml
deployment:
  name: example
  chain_id: <chain_id>

artifacts:
    dir: ./deployment/artifacts/
    filename: example.json

contracts:
  - MyToken:
      _totalSupplyOfTokens: 10000000000000000000000000
  - MyContractWithNoParameters
  - MyContractWithParameters:
      _token: $MyToken
      _number_parameter: 123456
      _list_parameter: [123456, 789012]
```

### 2. Create Deployment Script

Deployment scripts are located in `scripts/<domain>/<name>.py`.
Here is a simple example deployment script, but you can also find a full example in `scripts/lynx/deploy_root.py`:

```python
#!/usr/bin/python3

from ape import project

from deployment.constants import (
    CONSTRUCTOR_PARAMS_DIR,
)
from deployment.networks import is_local_network
from deployment.params import Deployer

VERIFY = not is_local_network()
CONSTRUCTOR_PARAMS_FILEPATH = CONSTRUCTOR_PARAMS_DIR / "my-domain" / "example.yml"


def main():
    deployer = Deployer.from_yaml(filepath=CONSTRUCTOR_PARAMS_FILEPATH,
                                  verify=VERIFY)
    token = deployer.deploy(project.MyToken)
    my_contract_with_no_parameters = deployer.deploy(
        project.MyContractWithNoParameters)
    my_contract_with_parameters = deployer.deploy(
        project.MyContractWithParameters)
    deployments = [
        token,
        my_contract_with_no_parameters,
        my_contract_with_parameters,
    ]
    deployer.finalize(deployments=deployments)
```

### 3. Setup Deployment Account (production only)

In order to deploy to **production** you will need to import an account into ape:
```
$ ape accounts import <id>
```
You will be asked to input the private key, and to choose a password. The account will then be available as `<id>`.

Then you can check the account was imported correctly:
```
$ ape accounts list
```

### 4. Deploy

Clear your ape database before deploying to production to avoid conflicts with upgradeable proxies.
Please note that this will delete all ape deployment artifacts, so make sure you have a
backup of artifacts from other projects before running this command.

```
$ rm -r ~/.ape/ethereum
```

Next, Run deployment scripts:
```bash

$ ape run <domain> <script_name> --network ethereum:local:test
$ ape run <domain> <script_name> --network polygon:amoy:infura
$ ape run <domain> <script_name>  --network ethereum:sepolia:infura
```

#### Testing on Local Forks
If you want to test on a local fork of a live network, for example when testing upgrades of contracts, 
you can use [`foundry`](https://getfoundry.sh/). 

Install `foundry` by running:

```bash
$ curl -L https://foundry.paradigm.xyz | bash
$ foundryup
```

Ensure that the following command runs:

```bash
$ anvil --version
```

Subsequently, you can run the respective deployment script by providing the relevant network:
- Sepolia: `--network ethereum:sepolia-fork:foundry`
- Amoy: `--network polygon:amoy-fork:foundry`

The script will be executed against the local fork based on the latest live block, allowing you to 
test contract deployments and interactions as if they were on the live network.


## NPM publishing process

For interoperability, we keep an NPM package with information of deployed smart contracts, such as address, ABI, etc.
The NPM package can be found at https://www.npmjs.com/package/@nucypher/nucypher-contracts.

The process to publish a new NPM release is as follows:

1. Make the required changes to deployment artifacts, usually by running a deployment script.

2. Update the package version using `bump2version`. We don't want to create a git tag, so we are running it with `--no-tag`.

Note that we follow [semantic versioning](https://docs.npmjs.com/about-semantic-versioning).

```bash
To update the minor version (e.g. from v1.1.0 to v1.2.0):
> bump2version minor --no-tag

To update the patch version (e.g. from v1.1.0 to v1.1.1):
> bump2version patch --no-tag
```

Alternatively, modify the `version` field in `package.json` and `setup.cfg`.

It is still necessary to bump the version on the `package-lock.json` file, so just run:

```bash
> npm install
```

3. Create a PR with these changes. We need this PR to be merged before continue.

4. When these changes are merged, create a new tag on `main` branch. The name of the tag must be the new `<version>` that is being released (e.g. `v0.23.0`).

```bash
> git tag -a <version> -m "<version>"

> git push origin <version>
```

5. Publish the new NPM version; this is performed automatically by Github Actions
when you [create a new release](https://github.com/nucypher/nucypher-contracts/releases/new),
associated to the latest version tag. Alternatively, run:

```bash
> npm publish
```
