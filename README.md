# SM64 iOS Builder

A Python console tool that runs in Linux or WSL, for compiling Super Mario 64 On Legacy iOS devices (iOS6+)


## Requirements

- Linux, or Windows 10/11 with WSL 2.
- Python 3, Git, and a working WSL account. The setup action installs missing
  Linux build prerequisites with `apt` and `sudo`.
- Network access to GitHub for Theos, the compiler toolchain, the iOS SDK, and
  the selected source repository.

Run from the shell:

```sh
cd /path/to/sm64-ios-builder
python3 app.py
```

The CLI has a standalone ROM check if you wish to check a rom beforehand:

```sh
python3 app.py --validate-rom "baserom.us.z64"
```

## First use

1. Choose **Set up Theos**. The builder installs Theos and its Linux iOS
   toolchain under `~/.local/share/sm64-ios-builder/theos`, downloads the
   iPhoneOS 6.1 SDK from [qianjigui/iOS-sdks](https://github.com/qianjigui/iOS-sdks),
   verifies the downloaded parts against GitHub's blob hashes, and builds a
   minimal armv7 Theos `.deb` as a preflight test. Setup is marked complete
   only after that test succeeds. The selected SDK is iOS 6.1; the app's
   minimum deployment target remains iOS 6.0.

2. Select the source repository (defaults to `JohnMama12/sm64`) and branch,
   then choose an iOS commit.

3. Select an authentic, legally obtained, big-endian `.z64` ROM. The only
   end-to-end supported version is US (NTSC-U), SHA-1
   `9bef1128717f958171a4afac3ed78ee2bb4e86ce`. JP, EU, and Shindou hashes are
   recognized but are not supported by this iOS build yet.
   If on windows You can paste a Windows drive path such as
   `C:\Users\YourUserName\Documents\baserom.us.z64`; the builder converts it to the
   corresponding WSL `/mnt/c/...` path.

4. Confirm you own the ROM and acknowledge the binary distribution restriction.
   The builder checks out the selected commit, runs `make assets VERSION=us`
   to use that source revision's existing Python extraction/build pipeline,
   then compiles the iOS app and writes a `.deb` under
   `~/.local/share/sm64-ios-builder/packages/`
   To it run on your device you should have iFile installed.
   On the iFile interface click the WiFi symbol to start the file server, note the device's IP and enter it on a web browser on your pc.
   It is suggested to upload the .deb to your downloads folder: `/var/mobile/Media/Downloads`. Select it and hit install.
   The app will refuse to run the game unless you place a copy of your rom (must be named exactly baserom.us.z64) under `/var/mobile/Documents`.
   If the app doesn't appear on SpringBoard you should run `uicache` in your   terminal or respring your device.

## Binary redistribution warning

The repository's main source is CC0-1.0, and the bundled `sm64tools` and
`n64graphics_ci` licenses are MIT. However, the full iOS game links the Fast3D
renderer in `src/pc/gfx/`; its `LICENSE.txt` explicitly prohibits redistribution
in binary form. The generated `.deb` is therefore for personal use only. Do
not upload or distribute it unless that renderer is replaced or its rightsholder
grants separate permission. This builder does not publish artifacts.
