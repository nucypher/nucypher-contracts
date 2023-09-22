from ape import networks, project

deployments = [
    project.LynxRootApplication.at('0xe9e6C183fadD057b8972E12471B212288b1ca6E6'),
    project.LynxTACoChildApplication.at('0x099a6128710F7e30Ed8740644F40EE6d3e6673D1'),
    project.LynxRitualToken.at('0x871EbA00295fF9c329dbCF2Cd329cd89FD926192'),
    project.Coordinator.at('0x7c8EA2d03fA65088fA85B889da365035555e4394'),
    project.GlobalAllowList.at('0xa7aF704855EA2a2513C56212D45b86287205520E'),
]

etherscan = networks.provider.network.explorer
for deployment in deployments:
    print(f"(i) Verifying {deployment.contract_type.name}...")
    etherscan.publish_contract(deployment.address)
