import { describe, expect, it } from 'vitest';

import { ChainId, type ContractName, type Domain, getContract } from '../src';

const testCases: Array<[ string, number, ContractName ]> = [
  [ 'lynx', 80001, 'Coordinator' ],
  [ 'lynx', 80001, 'GlobalAllowList' ],
  [ 'lynx', 80001, 'SubscriptionManager' ],
  [ 'tapir', 80001, 'Coordinator' ],
  [ 'tapir', 80001, 'GlobalAllowList' ],
  [ 'tapir', 80001, 'SubscriptionManager' ],
];

describe('registry', () => {
  for (const testCase of testCases) {
    const [ domain, chainId, contract ] = testCase;
    it(`should for domain ${domain}, chainId ${chainId}, contract ${contract}`, () => {
      const contractAddress = getContract(domain as Domain, chainId as ChainId, contract);
      expect(contractAddress).toBeDefined();
    });
  }
});
