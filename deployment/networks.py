from ape import networks


def is_local_network():
    return networks.network.name in ["local"]
