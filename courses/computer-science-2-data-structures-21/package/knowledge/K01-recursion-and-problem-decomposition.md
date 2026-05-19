# Recursion and Problem Decomposition

## Learning Goals

- Identify when a problem can be solved recursively.
- Write recursive functions with base cases and progress toward those base cases.
- Explain how the call stack represents unfinished work.
- Test recursive functions with normal, edge, and small inputs.

## Core Explanation

Recursion is a strategy where a function solves a problem by solving a smaller version of the same problem. A correct recursive function needs at least one base case and at least one recursive case. The base case stops the recursion. The recursive case reduces the problem so it moves toward the base case.

A helpful pattern is: define the simplest input, solve one small step, and delegate the smaller remaining problem to the recursive call. Recursion is not magic; each call waits for the next call to finish. The call stack stores these waiting calls.

## Key Terms

- Base case: the condition that stops recursion.
- Recursive case: the part of the function that calls itself.
- Call stack: the structure that tracks active function calls.
- Decomposition: breaking a problem into smaller problems.
- Edge case: an unusual input that may reveal incorrect assumptions.

## Common Mistakes

- Forgetting the base case.
- Writing a recursive call that does not make the input smaller.
- Handling only large examples and ignoring empty or one-item inputs.
- Using global variables when local return values would be clearer.
- Writing code that works accidentally but cannot be explained.

## Mini Examples

A recursive list sum has a base case for an empty list and a recursive case that adds the first item to the sum of the rest.

A recursive string reversal has a base case for an empty or one-character string and a recursive case that moves one character after reversing the rest.

## Preparation for Related Assignments

This note prepares students for A01 Recursive Problem Solving and for later tree traversal work. Students should practice explaining both what each function returns and how the input becomes smaller.
