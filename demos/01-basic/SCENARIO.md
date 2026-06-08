# Demo 01 - Basic: database connection pool exhaustion

A realistic SEV1 incident runbook for an orders API whose Postgres connection
pool gets exhausted under load, producing 5xx errors at checkout.

The input file `pool_exhaustion.runbook` uses RUNBOOKGEN's block format:
scalar fields (`title`, `severity`, `service`, ...), list sections
(`symptoms`, `detection`, ...), and a `steps` section where each item can
carry `owner=` and `expect=` annotations.

## Try it

Render the full Markdown runbook:

```sh
python -m runbookgen generate demos/01-basic/pool_exhaustion.runbook
```

Check completeness against the SRE checklist (exit code 2 if issues):

```sh
python -m runbookgen validate demos/01-basic/pool_exhaustion.runbook
```

Print the severity-driven escalation timeline (SEV1 = 5 min ack, IC + comms
required):

```sh
python -m runbookgen timeline demos/01-basic/pool_exhaustion.runbook
```

Machine-readable output for pipelines:

```sh
python -m runbookgen --format json generate demos/01-basic/pool_exhaustion.runbook
```

## Why this is useful

The severity profile drives the escalation timeline and the validation rules:
a SEV1 *must* list escalation contacts and a comms plan, and every step
should declare its expected outcome. Lower-severity runbooks relax those
requirements automatically, so the same template enforces the right rigor
for each incident class.
