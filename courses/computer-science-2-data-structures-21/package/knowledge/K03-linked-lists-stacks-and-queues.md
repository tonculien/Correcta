# Linked Lists, Stacks, and Queues

## Learning Goals

- Explain how nodes connect to form linked structures.
- Implement basic singly linked list operations.
- Build stack and queue behavior using clear interfaces.
- Handle empty, one-node, and multi-node edge cases.

## Core Explanation

A linked list stores data in nodes. Each node contains a value and a reference to the next node. Unlike an array-backed list, a linked list does not require elements to be stored next to each other in memory.

Stacks and queues are abstract data types. A stack follows last-in, first-out behavior. A queue follows first-in, first-out behavior. The implementation may use linked nodes, but the public interface should focus on behavior: push, pop, peek, enqueue, dequeue, and similar operations.

Correct linked structure code depends on careful reference updates. Many bugs come from forgetting to update the head, tail, or next reference when the structure is empty or has only one node.

## Key Terms

- Node: an object that stores data and a reference to another node.
- Head: the first node in a linked list.
- Tail: the last node in a linked list.
- Stack: a last-in, first-out collection.
- Queue: a first-in, first-out collection.
- Abstract data type: a behavior-focused description independent of implementation.

## Common Mistakes

- Losing access to part of a list by overwriting a reference too early.
- Forgetting to update tail when removing the last item.
- Returning node objects when the interface should return stored values.
- Ignoring operations on empty structures.
- Mixing stack and queue behavior by accident.

## Mini Examples

A stack can be implemented by adding and removing nodes at the head of a singly linked list.

A queue can be implemented efficiently by tracking both head and tail, adding at the tail, and removing from the head.

## Preparation for Related Assignments

This note prepares students for A03 Linked List, Stack, and Queue Implementation and for the final project. Students should test every operation on empty, single-item, and multi-item structures.
