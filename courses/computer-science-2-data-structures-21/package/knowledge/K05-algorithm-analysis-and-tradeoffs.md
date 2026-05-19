# Algorithm Analysis and Tradeoffs

## Learning Goals

- Explain time and space complexity using Big-O notation.
- Analyze loops, nested loops, recursion, and common data structure operations.
- Compare tradeoffs between different implementations.
- Connect complexity claims to actual code behavior.

## Core Explanation

Algorithm analysis estimates how resource usage grows as input size grows. Big-O notation describes an upper bound on growth. It does not measure exact runtime in seconds; it helps compare algorithms at scale.

Common complexity classes include O(1), O(log n), O(n), O(n log n), O(n^2), and O(2^n). A single loop over n items is often O(n). Nested loops over the same input are often O(n^2). Recursion depends on how many calls are made and how much work each call performs.

Good engineers also consider tradeoffs. A faster algorithm may use more memory. A simpler implementation may be easier to maintain but slower for large input. The right choice depends on the problem constraints.

## Key Terms

- Time complexity: how running time grows with input size.
- Space complexity: how memory usage grows with input size.
- Big-O: notation for asymptotic growth.
- Tradeoff: a design choice that improves one quality while weakening another.
- Worst case: the most expensive input pattern for an algorithm.

## Common Mistakes

- Treating Big-O as an exact runtime measurement.
- Ignoring space complexity.
- Claiming every recursive function is O(n) without analyzing calls.
- Forgetting that linked list indexing is not constant time.
- Making complexity claims without referencing specific code.

## Mini Examples

Pushing onto the head of a linked-list stack is O(1) because it changes only a small number of references.

Searching an unsorted linked list is O(n) because the target may require checking every node.

A balanced binary search tree can support O(log n) search, but an unbalanced tree can degrade to O(n).

## Preparation for Related Assignments

This note prepares students for A05 Algorithm Analysis Report and the final project explanation. Students should support each complexity claim with a reference to a specific loop, recursive call pattern, or data structure operation.
