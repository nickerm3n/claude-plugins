# Dependencies point inwards

Rule: domain code does not import from use cases, adapters, frameworks or infrastructure; use cases do not import adapters or infrastructure.
Why: business rules stay testable without the framework and survive a change of database, transport or UI.
Applies to: <fill in: e.g. src/domain/**, src/application/**>
Good: <fill in: path:line>
Bad: a domain entity importing an ORM model, an HTTP client or a UI component.
Exceptions: none without an ADR.

<!-- Example principle from the sdlc template: replace or delete it. -->
