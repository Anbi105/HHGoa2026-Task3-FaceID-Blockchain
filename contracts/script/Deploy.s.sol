// SPDX-License-Identifier: MIT
pragma solidity 0.8.24;

import "../src/EvidenceRegistry.sol";

interface Vm {
    function startBroadcast() external;
    function stopBroadcast() external;
}

contract DeployScript {
    Vm private constant vm = Vm(address(uint160(uint256(keccak256("hevm cheat code")))));

    function run() external returns (EvidenceRegistry registry) {
        vm.startBroadcast();
        registry = new EvidenceRegistry();
        vm.stopBroadcast();
    }
}