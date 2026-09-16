# Contributing

Thanks for looking. This is a small project with a strong opinion about checks, so a few things are worth saying up front.

## Getting set up

```
git clone https://github.com/PyGuy2000/k-mem.git
cd k-mem
python3 -m pip install pytest
python3 -m pytest
```

There are no runtime dependencies. The library is standard library only, so a hook can import it from any `python3` with no virtualenv. Keep it that way: a new import of a third-party package in `plugins/k-mem/lib/kmem/` will fail review.

Python 3.9 is the floor. CI runs 3.9, 3.11 and 3.13.

## Every check ships with a proof of red

A check that cannot fail is not a check. If you add one, add a fixture where the violation is present and the check must fail, next to the fixture where it passes. The audit tests show the pattern: each of the four docs checks has a red case and a green one.

The same rule applies to hooks, with one addition. A hook is only as good as the command that wires it, so its test runs the launcher as a subprocess with the payload shape Claude Code sends, and asserts the exit code. Testing the function directly once let a wiring fault turn every deny into an allow while the log kept saying "denied".

## Before you open a pull request

```
python3 -m pytest
python3 scripts/release_check.py
claude plugin validate . --strict
claude plugin validate plugins/k-mem --strict
```

The release check greps the tree for private names, hosts, paths and ticket ids. It fails on a hit. CI runs all four.

`claude plugin validate` passes some manifests the runtime refuses, so a change to `plugin.json`, `marketplace.json` or `hooks/hooks.json` needs a real install to prove it:

```
docker build -t kmem-fresh -f docker/Dockerfile .
docker run --rm -v "$PWD":/src kmem-fresh /src
```

That is the fresh-machine test. It adds the marketplace, installs the plugin, and runs the gate acceptance through the real launchers on a machine with no SSH key and no account. Two shipped bugs were caught only here.

## Writing

Documentation and commit bodies get the same care as code. Be specific, lead with the answer, and skip the decorative vocabulary. Say what a change does and what it fixes, with the evidence.

## Reporting a bug

Open an issue with the version (`kmem --version`), your operating system, the output of `kmem doctor`, and what you expected. If it involves the gate, `kmem report` is the most useful single thing you can paste.

For anything with a security dimension, read [SECURITY.md](SECURITY.md) first.

## Scope

The gate, the resolver, the notes tooling and the docs checks are the project. Things deliberately left out, with reasons, are in [docs/design.md](docs/design.md) under "What is deliberately not here". A proposal to add one of those is welcome, and it should start by arguing with the reason given.
