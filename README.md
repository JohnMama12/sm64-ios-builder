# SM64 iOS Builder

A Python console tool that runs inside WSL. It verifies a user-supplied US ROM,
selects an iOS source commit from GitHub, extracts game data in WSL, and builds
a local iOS `.deb` with Theos. It does not create a Windows game executable or
extract assets in the installed iOS app.

## Requirements

- Windows 10/11 with WSL 2 and a Linux distribution.
- Python 3, Git, and a working WSL account. The setup action installs missing
  Linux build prerequisites with `apt` and `sudo`.
- Network access to GitHub for Theos, the compiler toolchain, the iOS SDK, and
  the selected source repository.

Run from the WSL shell, not Windows Python:

```sh
cd /mnt/c/path/to/sm64-ios-builder
python3 app.py
```

The CLI has a standalone ROM check:

```sh
python3 app.py --validate-rom "/mnt/c/Users/you/ROMs/baserom.us.z64"
```

## First use

1. Choose **Set up Theos**. The builder installs Theos and its Linux iOS
   toolchain under `~/.local/share/sm64-ios-builder/theos`, downloads the
   iPhoneOS 6.1 SDK from [qianjigui/iOS-sdks](https://github.com/qianjigui/iOS-sdks),
   verifies the downloaded parts against GitHub's blob hashes, and builds a
   minimal armv7 Theos `.deb` as a preflight test. Setup is marked complete
   only after that test succeeds. The selected SDK is iOS 6.1; the app's
   minimum deployment target remains iOS 6.0, matching the port's existing
   settings and its iOS 6.1.3 test device.
2. Select the source repository (defaults to `JohnMama12/sm64`) and branch,
   then choose an iOS commit.
   The list is pinned to commit SHAs that touch `src/ios`; selecting one shows
   its message, changed files, and patch summary.
3. Select an authentic, legally obtained, big-endian `.z64` ROM. The only
   end-to-end supported version is US (NTSC-U), SHA-1
   `9bef1128717f958171a4afac3ed78ee2bb4e86ce`. JP, EU, and Shindou hashes are
   recognized for clear diagnostics but are not supported by this iOS build.
4. Confirm you own the ROM and acknowledge the local-only binary restriction.
   The builder checks out the selected commit, runs `make assets VERSION=us`
   to use that source revision's existing Python extraction/build pipeline,
   then compiles the iOS app and writes a `.deb` under
   `~/.local/share/sm64-ios-builder/packages/`.

The extraction step runs only in the WSL build workspace. It generates the C
and data inputs required by the iOS compiler; the Windows PC game executable
is never built, and the ROM is not put in the `.deb`.

The default source is `JohnMama12/sm64`, branch
`johnmama12-ios-app-publishing`. You can choose a different public GitHub
repository and branch from the CLI. A full app build also requires the user to
supply the supported ROM; the builder never downloads one.

The interactive terminal menu supports arrow keys and Enter, with number
shortcuts. Branches and commits use the same keyboard selector; `q` cancels a
selection or exits the main menu. When run without an interactive terminal,
the menu falls back to numbered prompts.

## Reproducibility

The build checks out the exact selected source commit SHA. Setup records the
installed Theos commit and toolchain release in
`~/.local/share/sm64-ios-builder/toolchain.json`, uses the fixed
`iPhoneOS6.1.sdk`, and does not silently update installed compiler versions.
The commit SHA, ROM SHA-1, and toolchain record identify a build. A later source
change therefore does not alter a build already pinned to an earlier commit.

## Binary redistribution warning

The repository's main source is CC0-1.0, and the bundled `sm64tools` and
`n64graphics_ci` licenses are MIT. However, the full iOS game links the Fast3D
renderer in `src/pc/gfx/`; its `LICENSE.txt` explicitly prohibits redistribution
in binary form. The generated `.deb` is therefore for local testing only. Do
not upload or distribute it unless that renderer is replaced or its rightsholder
grants separate permission. This builder does not publish artifacts.

The iOS SDK is downloaded into the user's WSL home and is not included in this
repository or the generated source. Theos is installed locally from its own
repository; neither third-party toolchain nor SDK binaries are checked in.

## Tests

```sh
python3 -m unittest discover -s tests -v
```
