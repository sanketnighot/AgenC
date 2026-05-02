// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

contract BountyEscrow {
    address public immutable arbiter;

    struct Bounty {
        address payable poster;
        uint256 amount;
        bool settled;
    }

    mapping(bytes32 => Bounty) public bounties;

    event BountyPosted(bytes32 indexed bountyId, address poster, uint256 amount);
    event BountyCompleted(bytes32 indexed bountyId, address[] workers, uint256[] amounts);
    event BountyRefunded(bytes32 indexed bountyId, address poster, uint256 amount);

    error AlreadyExists();
    error NotArbiter();
    error AlreadySettled();
    error ZeroValue();
    error LengthMismatch();
    error ExceedsAmount();

    modifier onlyArbiter() {
        if (msg.sender != arbiter) revert NotArbiter();
        _;
    }

    constructor(address _arbiter) {
        arbiter = _arbiter;
    }

    function postBounty(bytes32 bountyId) external payable {
        if (msg.value == 0) revert ZeroValue();
        if (bounties[bountyId].poster != address(0)) revert AlreadyExists();
        bounties[bountyId] = Bounty(payable(msg.sender), msg.value, false);
        emit BountyPosted(bountyId, msg.sender, msg.value);
    }

    function distribute(
        bytes32 bountyId,
        address payable[] calldata workers,
        uint256[] calldata amounts
    ) external onlyArbiter {
        if (workers.length != amounts.length) revert LengthMismatch();
        Bounty storage b = bounties[bountyId];
        if (b.settled) revert AlreadySettled();
        uint256 total;
        for (uint256 i; i < amounts.length; ++i) total += amounts[i];
        if (total > b.amount) revert ExceedsAmount();
        b.settled = true;
        for (uint256 i; i < workers.length; ++i) {
            workers[i].transfer(amounts[i]);
        }
        uint256 remainder = b.amount - total;
        if (remainder > 0) b.poster.transfer(remainder);
        emit BountyCompleted(bountyId, _toAddress(workers), amounts);
    }

    function refund(bytes32 bountyId) external onlyArbiter {
        Bounty storage b = bounties[bountyId];
        if (b.settled) revert AlreadySettled();
        b.settled = true;
        uint256 amount = b.amount;
        b.poster.transfer(amount);
        emit BountyRefunded(bountyId, b.poster, amount);
    }

    function _toAddress(address payable[] calldata a) internal pure returns (address[] memory out) {
        out = new address[](a.length);
        for (uint256 i; i < a.length; ++i) out[i] = a[i];
    }
}
