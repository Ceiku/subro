# Third-party notices

subro (FSL-1.1-ALv2) may optionally invoke external tools that are **not** part of this
repository.

## cplt (optional sandbox backend)

When `SUBRO_SANDBOX=cplt` is set, subro executes the [cplt](https://github.com/navikt/cplt)
binary if it is installed on the host. cplt is **not** bundled with subro.

- **Project:** https://github.com/navikt/cplt
- **License:** MIT License
- **Install:** `brew install navikt/tap/cplt` (or see cplt install docs)

Users who install cplt are subject to cplt's MIT license terms. subro's FSL license applies only
to subro's own source code.

## landlock-restrict (native Linux sandbox)

The vendored helper under `tools/landlock-restrict/` is used by the default native sandbox on
Linux.

- **License:** BSD-3-Clause (see `tools/landlock-restrict/landlock-restrict.c`)
