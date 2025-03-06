#!/usr/bin/env python3

import os

from ape_accounts import import_account_from_private_key


def main():
    try:
        passphrase = os.environ["DKG_INITIATOR_PASSPHRASE"]
        private_key = os.environ["DKG_INITIATOR_PRIVATE_KEY"]
    except KeyError:
        raise Exception(
            "There are missing environment variables."
            "Please set DKG_INITIATOR_PASSPHRASE and DKG_INITIATOR_PRIVATE_KEY."
        )
    account = import_account_from_private_key(
        'AUTOMATION',
        passphrase,
        private_key
    )
    print(f"Account imported: {account.address}")


if __name__ == '__main__':
    main()
