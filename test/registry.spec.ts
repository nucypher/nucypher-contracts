import { describe, expect, it } from "vitest";

import { ContractName, getContract } from "../src";

const testCases: [ string, number, ContractName ][] = [
  [ "lynx", 80001, "Coordinator" ],
  [ "lynx", 80001, "GlobalAllowList" ],
  [ "lynx", 80001, "SubscriptionManager" ],
  [ "tapir", 80001, "Coordinator" ],
  [ "tapir", 80001, "GlobalAllowList" ],
  [ "tapir", 80001, "SubscriptionManager" ]
];

describe("registry", () => {
  for (const testCase of testCases) {
    const [ domain, chainId, contract ] = testCase;
    it(`should for domain ${domain}, chainId ${chainId}, contract ${contract}`, () => {
      const contractAddress = getContract(domain, chainId, contract);
      expect(contractAddress).toBeDefined();
    });
  }
});
