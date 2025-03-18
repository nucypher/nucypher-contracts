# How to run the DKG workflow locally with act

To run the DKG workflow locally, you need to have act installed. 

https://github.com/nektos/act

You also need to have a `.env.local` and `.secrets` file completed with the necessary environment
variables (see `.env.act` and `.secrets.act.template`).

Then you can run the following command:

```bash
act workflow_dispatch -j initiate_dkg --secret-file .github/.secrets --container-architecture linux/amd64 --env-file .github/.env.local --artifact-server-path /tmp/artifacts
```