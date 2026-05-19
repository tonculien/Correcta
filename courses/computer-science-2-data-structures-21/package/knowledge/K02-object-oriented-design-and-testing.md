# Object-Oriented Design and Testing

## Learning Goals

- Design classes that represent clear concepts.
- Use constructors, methods, and instance variables appropriately.
- Keep object state valid through encapsulation.
- Write tests that check behavior rather than implementation details.

## Core Explanation

Object-oriented design organizes code around objects that combine state and behavior. A good class has a focused responsibility. Its public methods should make sense to another programmer without requiring them to inspect private details.

Encapsulation means the class protects its own state. Instead of letting every part of a program modify internal data directly, a class exposes methods that enforce rules. This makes code easier to test and harder to misuse.

Testing is part of design. A class should be easy to construct, use, and verify. Good tests cover ordinary cases, edge cases, and invalid inputs when relevant.

## Key Terms

- Class: a blueprint for objects.
- Object: an instance of a class.
- Encapsulation: protecting internal state behind a public interface.
- Method: a function attached to an object.
- Invariant: a rule that should remain true for an object.
- Unit test: a test of a small part of a program.

## Common Mistakes

- Creating classes with too many unrelated responsibilities.
- Making every variable public and letting outside code mutate state freely.
- Writing tests that only print output instead of asserting expected behavior.
- Ignoring invalid inputs.
- Designing methods that depend on hidden global state.

## Mini Examples

A `Task` class might store a title, priority, and completion status. Methods could include `mark_complete`, `rename`, and `is_overdue`.

A `Playlist` class might store songs and provide methods such as `add_song`, `remove_song`, `move_song`, and `total_duration`.

## Preparation for Related Assignments

This note prepares students for A02 Object-Oriented Module Design and the final project. Students should be ready to justify why each class exists and how tests prove its behavior.
