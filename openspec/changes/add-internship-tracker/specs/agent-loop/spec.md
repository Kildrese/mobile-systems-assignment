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

### Requirement: Every agent turn is a tool call
When tools are offered, each model call SHALL require a tool call (`tool_choice: required`), so a model cannot spend a step, or its last step, on a text-only reply. A 400 from the provider meaning the model's output could not be used (Groq's `tool_use_failed` or `output_parse_failed`) SHALL be treated as the model's mistake: the model is told and the loop continues; it is not a provider failure.

#### Scenario: Finish written as text
- **WHEN** the Scout's last call offers only `finish`
- **THEN** the request requires a tool call, so the reply is a `finish` call, not the note as plain text

#### Scenario: Unparseable output
- **WHEN** Groq answers `400 output_parse_failed` to an Editor call
- **THEN** the Editor is told its output could not be parsed and tries again, and no later stage is skipped

### Requirement: A caller can end an agent when its work is done
A caller of the agent loop MAY pass a check that runs after each reply's tool calls. When the check returns a result, the loop SHALL stop as if `finish` had been accepted with that result, without another model call.

#### Scenario: Curator batch handled
- **WHEN** the Curator's tool call handles the last pending posting of its batch
- **THEN** the batch ends without a `finish` call
