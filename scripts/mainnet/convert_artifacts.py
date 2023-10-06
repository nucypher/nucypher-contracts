from pathlib import Path

from deployment.confirm import _continue
from deployment.constants import ARTIFACTS_DIR
from deployment.legacy import convert_legacy_npm_artifacts

INPUT_DIR = Path(__file__).parent.parent.parent / "artifacts"
OUTPUT_FILEPATH = ARTIFACTS_DIR / "mainnet.json"


def main():
    print(f"input_dir: {INPUT_DIR.absolute()}")
    _continue()

    convert_legacy_npm_artifacts(
        directory=INPUT_DIR,
        chain_id=1,
        output_filepath=OUTPUT_FILEPATH
    )
