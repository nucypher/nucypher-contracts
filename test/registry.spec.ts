import { describe, expect, it } from "vitest";

import { ChainId, type ContractName, contractNames, type Domain, getContract } from "../src";

const testCases: Array<[string, number, ContractName]> = contractNames.flatMap((contract) => [
  ["lynx", 80002, contract],
  ["tapir", 80001, contract],
  ["mainnet", 137, contract],
]);

describe("registry", () => {
  it.each(testCases)(
    `should work for domain %s, chainId %i, contract %s`,
    (domain, chainId, contract) => {
      const contractAddress = getContract(domain as Domain, chainId as ChainId, contract);
      expect(contractAddress).toBeDefined();
    },
  );

  it("should throw for invalid domain", () => {
    expect(() => getContract("invalid-domain", 80001, "Coordinator")).toThrow();
  });

  it("should throw for invalid chainId", () => {
    expect(() => getContract("lynx", 0, "Coordinator")).toThrow();
  });

  it("should throw for invalid contract", () => {
    expect(() => getContract("lynx", 80001, "InvalidContract")).toThrow();
  });

  it("should return the same contract address for the same domain, chainId, and contract", () => {
    const contractAddress1 = getContract("lynx", 80002, "Coordinator");
    const contractAddress2 = getContract("lynx", 80002, "Coordinator");
    expect(contractAddress1).toEqual(contractAddress2);
  });

  it("should return different contract addresses for different domains", () => {
    const contractAddress1 = getContract("lynx", 80002, "Coordinator");
    const contractAddress2 = getContract("tapir", 80001, "Coordinator");
    expect(contractAddress1).not.toEqual(contractAddress2);
  });
});
