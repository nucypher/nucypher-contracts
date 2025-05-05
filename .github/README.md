# How to run the DKG workflow locally with act

To run the DKG workflow locally, you need to have act installed.

https://github.com/nektos/act

Verify the values in `.env.lynx.act` and `.secrets` file completed with the
necessary environment variables (see the template files in the same directory `.secrets.act.template`).

Then you can run the following command:

```bash
act workflow_dispatch -j initiate_dkg \
--var-file .github/.env.lynx.act \
--secret-file .github/.secrets.act \
--container-architecture linux/amd64 \
--artifact-server-path /tmp/artifacts
```
