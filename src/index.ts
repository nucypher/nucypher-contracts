import lynxRegistryJson from "../deployment/artifacts/lynx.json";
import mainnetRegistryJson from "../deployment/artifacts/mainnet.json";
import tapirRegistryJson from "../deployment/artifacts/tapir.json";

export type Abi = unknown;

export interface DeployedContract {
  address: string;
  abi: Abi;
}

// Only expose contracts that are used in the SDK
export const contractNames = ["Coordinator", "GlobalAllowList", "SubscriptionManager"] as const;

export type ContractName = (typeof contractNames)[number];

export interface Contract {
  name: ContractName;
  abi: Abi;
}

export type ContractRegistry = Record<string, Record<string, DeployedContract>>;

export const domainRegistry: Record<string, ContractRegistry> = {
  lynx: lynxRegistryJson,
  tapir: tapirRegistryJson,
  mainnet: mainnetRegistryJson,
};

export type Domain = "mainnet" | "oryx" | "tapir" | "lynx";

export type ChainId = 1 | 5 | 137 | 80002;

export type ChecksumAddress = `0x${string}`;

export const getContract = (
  domain: Domain | string,
  chainId: ChainId | number,
  contract: ContractName | string,
): ChecksumAddress => {
  if (!contractNames.includes(contract as ContractName)) {
    throw new Error(`Invalid contract name: ${contract}`);
  }

  const registry = domainRegistry[domain];
  if (!registry) {
    throw new Error(`No contract registry found for domain: ${domain}`);
  }

  const contracts = registry[chainId as ChainId];
  if (!contracts) {
    throw new Error(`No contracts found for chainId: ${chainId}`);
  }

  const deployedContract = contracts[contract];
  if (!deployedContract) {
    throw new Error(`No contract found for name: ${contract}`);
  }

  return deployedContract.address as ChecksumAddress;
};
