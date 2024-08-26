import click
from eth_utils import to_checksum_address


class MinInt(click.ParamType):
    name = "minint"

    def __init__(self, min_value):
        self.min_value = min_value

    def convert(self, value, param, ctx):
        try:
            ivalue = int(value)
        except ValueError:
            self.fail(f"{value} is not a valid integer", param, ctx)
        if ivalue < self.min_value:
            self.fail(
                f"{value} is less than the minimum allowed value of {self.min_value}", param, ctx
            )
        return ivalue


class ChecksumAddress(click.ParamType):
    name = "checksum_address"

    def convert(self, value, param, ctx):
        try:
            value = to_checksum_address(value=value)
        except ValueError:
            self.fail("Invalid ethereum address")
        else:
            return value
