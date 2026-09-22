# Physical firmware provenance

Read this only when a task needs exact physical firmware/source/image/build identity.

Do not infer physical firmware from branch names, host checkout, operator-stated target or presumed flashing. Obtain provenance from the physical node.

Preferred command:

```text
/version
```

Current integrity-capable Chatter may report:

```text
[SYS] FIRMWARE Chatter git=<40-hex> state=<clean|dirty|unknown> env=<pio-env>
[SYS] FIRMWARE IMAGE validation_sha256=<64-hex> status=<OK|...> slot=<0|1>
[SYS] BUILD META toolchain_sha256=<64-hex> pio=<version>
```

## Source SHA

Exact source SHA is established only when:

```text
git=<exact 40-hex> AND state=clean
```

If state=dirty, the Git value is only a base commit. Preserve it as evidence, but exact source provenance is unknown.

If state=unknown, git=unknown, or canonical provenance is unsupported, exact firmware SHA is unknown.

MANIFEST.json firmware.sha is exact source Git SHA or literal unknown.

Never place validation_sha256 or toolchain_sha256 into firmware.sha.

## Running image and build metadata

validation_sha256 is runtime ESP application-image identity. It is not the SHA-256 of the whole firmware.bin file.

toolchain_sha256 identifies the canonical build/toolchain record. It is not source Git identity.

A release-manifest artifact.sha256 is an external whole-file artifact digest and is not reported directly by the node.

When an exact running-image release gate is requested:

```text
node status == OK
AND
node validation_sha256 == expected artifact.image_validation_sha256
```

When exact build metadata is requested:

```text
node toolchain_sha256 == expected toolchain.sha256
```

A required provenance/integrity mismatch discovered before measured behavior is a precondition BLOCKED, not an RF/ACK behavior FAIL.

Do not flash automatically to repair a mismatch.

When both physical nodes must use one exact checkpoint, establish the required provenance independently on both nodes.
