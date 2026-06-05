# Third-party notices

subro (FSL-1.1-ALv2) may optionally invoke external tools that are **not** part of this
repository.

## cplt (optional sandbox backend)

When `SUBRO_SANDBOX=cplt` is set, subro executes the [cplt](https://github.com/Ceiku/cplt)
binary if it is installed on the host. cplt is **not** bundled with subro.

- **Project:** https://github.com/Ceiku/cplt (fork of [navikt/cplt](https://github.com/navikt/cplt))
- **License:** MIT License
- **Install:** see [docs/cplt.md](docs/cplt.md)

Users who install cplt are subject to cplt's MIT license terms. subro's FSL license applies only
to subro's own source code.

## landlock-restrict (native Linux sandbox)

On Linux, the default native backend uses an external `landlock-restrict` helper when available
(`SUBRO_LANDLOCK_RESTRICT` or on `PATH`). It is **not** bundled with subro.
