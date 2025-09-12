import click
from ape.cli import ConnectedProviderCommand
from eth_account import Account

BASE_PATH = "m/44'/1'/0'/0/{}"  # testnet derivation path for accounts
BIP39_PASSPHRASE = ""  # optional; set if you used one in your wallet
COUNT = 5  # how many to derive


Account.enable_unaudited_hdwallet_features()


@click.command(cls=ConnectedProviderCommand)
@click.option(
    "--mnemonic-file",
    "-m",
    help="File with mnemonic to use for account derivation",
    type=click.Path(exists=True),
    required=True,
)
@click.option(
    "--passphrase",
    "-p",
    help="Optional passphrase for the mnemonic",
    type=click.STRING,
    default=BIP39_PASSPHRASE,
    required=False,
)
@click.option(
    "--count", "-c", help="Number of accounts to derive", type=int, default=COUNT, required=False
)
def cli(mnemonic_file, passphrase, count):
    """Derive testnet accounts from a mnemonic."""
    with open(mnemonic_file, "r") as f:
        # only the first line is used
        mnemonic = f.readline().strip()

    for i in range(count):
        path = BASE_PATH.format(i)
        account = Account.from_mnemonic(mnemonic, passphrase=passphrase, account_path=path)
        print(f"Account {i} (Path - {path}):")
        print(f"\tAddress: {account.address} ")
        print(f"\tPrivate Key: {account.key.hex()}")
        print("----------------------------------")


if __name__ == "__main__":
    cli()
