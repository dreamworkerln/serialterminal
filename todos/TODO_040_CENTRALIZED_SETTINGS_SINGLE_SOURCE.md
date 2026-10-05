# Centralized settings / single-source-of-truth TODO

TODO-ID: TODO_040
Status: OPEN
Related: `TODO_039_TUI_MAIN_MENU_AND_BAUD_SELECTOR`
Finding checkpoint: `dev_tui@2682f1c4a3cd077bdffe49e3989d6856e1402795`

## Purpose

Refactor SerialTerminal so important user-facing/runtime policy defaults have one authoritative definition instead of being duplicated as unrelated literals across transport constructors, device selection, CLI parser defaults and UI code.

The immediate concrete example is Serial baud rate. During the current 921600 transition the same default has existed in several places, including `SerialTransport`, `DeviceSelector` and more than one CLI parser path. A change that is intended to alter one policy must not require finding and editing the same numeric value in several modules.

The goal is **single source of truth**, not a giant dumping ground for every constant in the repository.

## Core rule

If several parts of SerialTerminal are expressing the **same configuration/policy decision**, that decision must be defined once and consumed by those parts.

Bad pattern:

```python
# transport.py
baud: int = 921600

# cli.py
parser.add_argument("-b", default=921600)

# selector.py
DeviceSelector(..., baud=921600)

# some future UI code
DEFAULT_BAUD = 921600
```

These are not four independent facts. They are one policy copied four times.

Target pattern:

```text
one authoritative settings/defaults definition
        ↓
CLI resolution
DeviceSelector
SerialTransport construction
TUI presentation/runtime selector
```

No consumer should need to know the literal default independently.

## Scope

Create one central settings/defaults module, tentatively:

```text
src/serialterminal/settings.py
```

The exact filename may change during implementation if an existing module provides a clearly better ownership boundary, but there must be one obvious authoritative place for shared operational defaults.

The central settings layer should cover **important shared values**, for example where applicable:

- default Serial baud policy;
- profile-aware Serial baud defaults (`generic/default`, `chatter`);
- commonly shared reconnect/scan/operator-facing timeout defaults when they are genuinely the same policy across multiple callers;
- default receive/log locations or related user-facing defaults if currently duplicated and semantically identical;
- user-visible operational limits/options that multiple frontends or constructors must agree on;
- other duplicated literals discovered by the audit where changing one value should logically change all consumers.

This list is illustrative, not a requirement to move every named constant.

## Explicit non-goal: do not centralize everything

Do **not** turn the settings file into a global constants landfill.

The following normally stay with the code/protocol that owns them:

- FT1 wire magic/version/message type values;
- packet/header sizes that are part of a wire format;
- protocol MTU-derived constants;
- parser grammar tokens;
- internal enum values;
- private implementation thresholds used in one module only;
- local buffer sizes with no shared configuration meaning;
- test-only constants;
- values whose meaning is inseparable from one subsystem and which are not user/runtime policy;
- hardware/protocol constants that should be owned by a profile or protocol implementation rather than by generic SerialTerminal settings.

A value should not be moved merely because it is numeric or uppercase.

## Avoid a new global-state problem

Centralization must **not** be implemented as dozens of mutable module globals.

Preferred shape is one small immutable/typed structure or a small number of cohesive immutable structures, for example conceptually:

```python
@dataclass(frozen=True)
class SerialDefaults:
    generic_baud: int
    chatter_baud: int

@dataclass(frozen=True)
class TerminalDefaults:
    serial: SerialDefaults
    # only genuinely shared operational defaults

DEFAULTS = TerminalDefaults(...)
```

or an equivalent immutable representation.

Small pure resolver helpers are acceptable and encouraged:

```text
resolve_serial_baud(profile, explicit_baud)
```

The important properties are:

- authoritative values are defined once;
- consumers do not copy literals;
- settings are not mutable process-wide state;
- import direction is simple and does not introduce circular dependencies;
- runtime overrides are explicit values passed into session/transport objects rather than mutation of shared defaults.

## Baud-rate policy integration

TODO_039 defines the intended baud behavior:

```text
explicit -b / --baud
    -> explicit value always wins

no explicit baud:
    chatter         -> 921600
    generic/default -> 115200
```

TODO_040 should provide the single authoritative configuration source that TODO_039 consumes.

The CLI parser should therefore be able to distinguish:

```text
operator explicitly supplied baud
```

from:

```text
operator omitted baud; resolve profile default
```

Using a parser literal such as `default=921600` in multiple command parsers is not acceptable as the final architecture. A parser-level `None`/sentinel followed by one shared resolver is the expected direction unless implementation review identifies a stronger equivalent design.

Likewise, `SerialTransport` and `DeviceSelector` must not independently redefine the same profile/default policy. They should receive a resolved baud or consume the same authoritative resolver/default object, depending on the final ownership design.

## Configuration ownership rule

Before moving a value, classify it:

### A. Shared operational setting

Examples:

```text
default serial baud
scan duration shared by CLI + selector
one common reconnect delay policy
```

If multiple callers mean the **same thing**, centralize it.

### B. Profile-owned policy

If a value varies because the device/profile defines the behavior, the central settings layer may hold the fallback/default mapping or call a profile-owned resolver, but do not erase profile ownership merely to put a number in one file.

The final dependency direction should remain clear.

### C. Local implementation constant

If only one subsystem owns the meaning, keep it there.

### D. Protocol/wire constant

Keep it with the protocol implementation.

This classification is part of the implementation review, not optional cleanup.

## Repository audit

Before implementation, perform a bounded audit for duplicated configuration-like literals/defaults.

At minimum inspect:

- `src/serialterminal/cli.py`;
- `src/serialterminal/transports/*`;
- device selector/discovery paths;
- TUI/frontend constructor defaults;
- profile defaults;
- agent/session startup defaults;
- log/receive-directory defaults;
- common reconnect/scan/timeout parameters.

The audit should produce a short table in this TODO or implementation commit notes:

```text
value/policy | current owners | same semantic policy? | action
```

Only semantically identical shared policy should move.

Do not mechanically deduplicate equal numbers that happen to have different meanings.

## Consumer contract

After refactoring, constructors should prefer receiving resolved values explicitly where practical.

For example:

```text
CLI/profile resolver
    -> resolved baud
    -> DeviceSelector
    -> SerialTransport
```

rather than having each layer silently pick its own default.

This makes tests and future overrides deterministic and keeps runtime state local to the owning object.

## User configuration versus built-in defaults

This TODO is primarily about **code-level single-source defaults/policy**.

It does not automatically require a persistent user configuration file on disk (`~/.config/...`) unless separately selected later.

The phrase “settings file” in this TODO means a centralized source module for application defaults/configuration policy. A future persisted user-preferences layer may consume the same typed settings model, but is not required for closure here.

## Compatibility

Refactoring must preserve explicit CLI behavior and existing transport APIs unless an intentional change is already specified by TODO_039.

In particular:

- `-b/--baud` remains supported;
- explicit baud remains authoritative;
- BLE behavior is not affected by Serial baud defaults;
- SPP behavior must not accidentally inherit USB-Serial-only policy;
- generic profile remains usable with ordinary 115200 devices after TODO_039 policy is applied;
- chatter uses the accepted 921600 default once the current firmware work has settled;
- agent and human frontends must not silently diverge in defaults when they use the same underlying setting.

## Tests / acceptance

Automated coverage must include at least:

- one authoritative baud/default source is used by all serial startup paths;
- generic without explicit baud resolves to 115200;
- chatter without explicit baud resolves to 921600;
- explicit `-b` overrides profile default;
- `serial` CLI and unified `auto` produce the same resolution semantics;
- `DeviceSelector` and `SerialTransport` do not silently substitute a second conflicting default;
- profile switching/recreation uses the expected resolved setting according to TODO_039 semantics;
- BLE/non-Serial paths are unaffected;
- relevant agent/human startup paths agree where they share the setting;
- no regression in existing device-selection/reconnect behavior.

Add targeted regression coverage for each duplicated policy removed during the audit when practical.

A lightweight source-level regression check is acceptable for especially important single-source policies (for example asserting that baud defaults are not independently redefined in multiple production modules), but avoid brittle tests that simply grep every numeric literal in the repository.

## Implementation checklist

- [ ] Audit duplicated configuration-like defaults and classify ownership.
- [ ] Select/create one central settings/defaults module.
- [ ] Use immutable typed settings/default structures or an equivalent non-mutable design.
- [ ] Centralize Serial baud policy first.
- [ ] Integrate TODO_039 profile-aware baud resolution.
- [ ] Make CLI omission distinguishable from explicit override.
- [ ] Remove duplicated baud literals/default-policy definitions from constructors/parsers.
- [ ] Centralize other genuinely shared important defaults found by the audit.
- [ ] Leave protocol/wire and local implementation constants with their owners.
- [ ] Avoid mutable global runtime configuration.
- [ ] Update tests.
- [ ] Update documentation/help where defaults are displayed.
- [ ] Review `BASE..HEAD` diff and all deletions.
- [ ] Run targeted tests.
- [ ] Run full repository CI.

## Acceptance criteria

TODO_040 is complete when:

1. Important shared operational defaults have one obvious authoritative source.
2. Serial baud policy is no longer independently hardcoded in several production locations.
3. TODO_039's profile-aware baud defaults and explicit CLI override consume that source.
4. Runtime overrides are object/session state, not mutation of module globals.
5. Equal numeric values with unrelated semantics have **not** been mechanically merged.
6. Wire/protocol ownership remains local and clear.
7. Generic/Chatter/explicit-baud startup tests prove the selected behavior.
8. Full CI passes.

## Design principle

The intended rule for future development is:

> Define a shared configuration decision once. Pass or resolve that decision where it is used. Do not copy the same default literal into every layer merely because each layer can accept the value.

At the same time:

> Do not centralize constants that are not configuration. Local ownership is better than a giant global constants module.
