# Versioning

The builder and the iOS source have independent version sequences. Builder
versions identify changes to this Linux/WSL CLI; source versions identify the
game/app code the CLI can build. Use annotated Git tags and matching GitHub
Releases in the form `vMAJOR.MINOR.PATCH[-beta.N]`. Do not tag ordinary commits
or source tweaks as builder versions.

## What to increment

| Change to the builder | Version change |
| --- | --- |
| Fix a bug without changing the documented CLI or build workflow | Increment `PATCH` after a stable release |
| Add a backwards-compatible CLI option, platform support, or build capability | Increment `MINOR` after a stable release |
| Remove or incompatibly change a CLI interface, saved-state format, or build workflow | Increment `MAJOR` after `1.0.0` |
| Publish another build of the same beta target | Increment `beta.N`, for example `v0.1.0-beta.1` to `v0.1.0-beta.2` |
| Start a new beta cycle with materially expanded scope | Increment `MINOR` and reset beta to 1, for example `v0.1.0-beta.2` to `v0.2.0-beta.1` |

Before `1.0.0`, the CLI and its saved state are not considered stable; use a
`MINOR` version for an incompatible change and reserve `PATCH` for compatible
fixes. After `1.0.0`, use `MAJOR` for breaking changes.

## Current beta sequence

The latest published builder beta is `v0.1.0-beta.1`. The release-and-branch
source picker begins a new feature beta cycle at `v0.2.0-beta.1`, tagged on a
development branch. Further builder changes within this cycle use
`v0.2.0-beta.2`, `v0.2.0-beta.3`, and so on. When ready, publish stable
`v0.2.0` from `main`. After that, a compatible bug fix is `v0.2.1`, a
backwards-compatible feature is `v0.3.0`, and a breaking change is `v1.0.0`
(or the next major version).

## Keep source versions separate

The source picker defaults to the newest published GitHub Release from the
selected source repository; branches are an explicit option for development
builds. `master` is the stable source branch. Non-`master` branches are
development/testing targets and are not releases. Releases are immutable
version references, while branches can move. Branch packages include the
selected branch name and resolved commit hash, so each build remains
identifiable. Use the source repository's versioning policy to decide when its
source version changes; do not increment the builder version just because a new
source release is available. Increment the builder version when the CLI or its
own build behavior changes. Conversely, a builder-only change does not require
a new iOS source release.

The Debian package version includes the selected source reference and resolved
source commit, so packages built from different releases or branch commits
remain identifiable. This package version is not the builder version.

## Release checklist

1. Run the builder tests and verify setup/build behavior for the change.
2. Update the README or this policy if supported platforms, requirements, or
   version behavior changed.
3. Keep `main` as the stable line and do development on feature branches.
   Prerelease beta tags may point to a development-branch commit; stable tags
   must point to `main`. Publish a matching GitHub Release with concise notes
   describing user-visible changes and known limitations.
4. Never move or reuse a published version tag. Keep release assets free of
   generated game binaries; the source renderer license prohibits binary
   redistribution.
