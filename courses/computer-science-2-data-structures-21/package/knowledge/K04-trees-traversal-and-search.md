# Trees, Traversal, and Search

## Learning Goals

- Describe tree structure using roots, children, leaves, and subtrees.
- Implement recursive tree traversal.
- Compare preorder, inorder, postorder, and breadth-first traversal.
- Use search logic to find values in a tree.

## Core Explanation

A tree is a hierarchical data structure made of nodes. Each node may have child nodes. A binary tree is a tree where each node has at most two children. Trees are naturally recursive because each child can be treated as the root of a smaller tree.

Traversal means visiting every node in a structured order. Preorder visits the current node before its children. Inorder visits the left subtree, current node, then right subtree. Postorder visits children before the current node. Breadth-first traversal visits nodes level by level, often using a queue.

Search checks whether a target value exists. A general binary tree may require checking many nodes. A binary search tree can search more efficiently if values are ordered correctly.

## Key Terms

- Root: the top node of a tree.
- Leaf: a node with no children.
- Subtree: a tree formed from a node and its descendants.
- Traversal: a method for visiting nodes.
- Binary tree: a tree where each node has at most two children.
- Breadth-first search: level-by-level search.
- Depth-first search: branch-first search.

## Common Mistakes

- Confusing traversal order names.
- Forgetting the base case for an empty subtree.
- Assuming every binary tree is a binary search tree.
- Returning too early before checking both children.
- Using traversal output without explaining why that order matters.

## Mini Examples

A preorder traversal can be useful for copying a tree structure because it processes a parent before its children.

A postorder traversal can be useful for deleting or evaluating a tree because it processes children before the parent.

## Preparation for Related Assignments

This note prepares students for A04 Tree Traversal and Search and for final projects that use hierarchical data. Students should be able to trace traversal output by hand for a small tree.
