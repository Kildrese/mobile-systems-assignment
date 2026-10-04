# Spec Delta

## ADDED Requirements

### Requirement: The last step offers only finish
When an agent has one model call left before a step limit (its own or the run's), or when its token budget left (its own, or the run's less the reserve) is smaller than its last call's prompt and reply plus one more reply, the runtime SHALL offer only `finish` for that call and tell the model it is the last step, so the agent can end with its result instead of being stopped by the limit.

#### Scenario: Scout on its last step
- **WHEN** the Scout has used 11 of its 12 steps
- **THEN** its 12th model call is sent with `finish` as the only tool and a message saying it is the last step

#### Scenario: Token budget nearly used
- **WHEN** the Scout has 8,000 tokens, and its first call used 4,500
- **THEN** its second call is sent with `finish` as the only tool, because a call resending at least that much cannot fit with a reply

### Requirement: A caller can end an agent when its work is done
A caller of the agent loop MAY pass a check that runs after each reply's tool calls. When the check returns a result, the loop SHALL stop as if `finish` had been accepted with that result, without another model call.

#### Scenario: Curator batch handled
- **WHEN** the Curator's tool call handles the last pending posting of its batch
- **THEN** the batch ends without a `finish` call
