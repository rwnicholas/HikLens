# Hikvision Linux SDK integration helper

This directory contains the locally built helper used by the application's
optional HCNetSDK + PlayCtrl capture backend, plus a standalone diagnostic
executable. The proprietary SDK itself is not included.

## Download and extract the SDK

Use Hikvision's official [HiTools SDK download page](https://www.hikvision.com/en/support/tools/hitools/clf4633a00e385d6ea/)
to obtain the **Device Network SDK for Linux 64-bit** package matching the
host CPU architecture. The x86-64 package validated with this integration is
**V6.1.11.40, build 20260922**. Download access and use are subject to
Hikvision's account and license terms.

Extract the archive outside the application repository, for example:

```text
~/Downloads/EN-HCNetSDKV6.1.11.40_build20260922_linux64/
```

The SDK root used below must contain `lib/`, `incEn/`, and `QtDemo/`.
Install `make` and a C++17 compiler (`g++`), then build the application helper:

```sh
make -C hikvision-sdk helper \
  SDK_ROOT="$HOME/Downloads/EN-HCNetSDKV6.1.11.40_build20260922_linux64"
```

This installs the helper to
`~/.local/lib/hikvision-camera-viewer/hikvision_stream_helper`. The executable
links to the selected external SDK and is not placed in the repository.
The same build and SDK initialization check are available in the application's
Settings through **Build / Verify Helper** after choosing the SDK directory.

## Configure the application

Open **Settings** in the viewer and set:

- **Hikvision SDK Directory** to the extracted SDK root (not its `lib/`
  subdirectory). Alternatively, set `HIKVISION_SDK_DIR` before starting the
  application.
- **Hikvision SDK Port** to the DVR's SDK port, normally `8000`.
- **Username** and **Password** to a DVR account with live-view permission.
- **Streaming Verification Code** to the separate Platform Access stream
  encryption code; it is not the DVR account password.

Select **Hikvision SDK (encrypted stream)** from the toolbar's **Engine**
selector. The application checks required libraries and host architecture and
runs an SDK initialization check before capture. It reports missing or
incompatible dependencies instead of silently switching backends.

The SDK and PlayCtrl run in a separate helper process with a headless EGL
configuration; the Qt application keeps its normal Wayland or X11 session.
The existing HTTP and RTSP/FFmpeg backends do not depend on this SDK.

## Encryption and validation

The helper uses the 16-byte result of `NET_DVR_GET_AES_KEY` with
`NET_DVR_SetSDKSecretKey`. Separately, it supplies the Platform Access
Streaming Verification Code to `PlayM4_SetSecretKey` before opening the
PlayCtrl stream. The application reports the code as applied only if PlayCtrl
accepts the call, and only displays decoded frames.

On the tested `iDS-7204HQHI-M1/T`, the configured code produced decoded video
through the application pipeline: channel 1 sub-stream at 960x480 and
main-stream at 1920x1088. This result applies to that device/configuration and
does not guarantee compatibility with all Hikvision models or firmware.
Changing the stream encryption code on the DVR is not part of SDK setup.

For a standalone diagnostic run, build the test executable:

```sh
make -C hikvision-sdk
```

Set credentials in the environment (do not enter actual credentials directly
in shell command history), then run it:

```sh
export HIKVISION_HOST='DVR_IP_ADDRESS'
export HIKVISION_PORT=8000
export HIKVISION_USERNAME='...'
export HIKVISION_PASSWORD='...'
export HIKVISION_STREAM_VERIFICATION_CODE='...'
export HIKVISION_CHANNEL=1
export HIKVISION_RUN_SECONDS=15
make -C hikvision-sdk run
```

Replace the example host and credential placeholders with your DVR's values.
The diagnostic defaults to the main stream; set `HIKVISION_STREAM_TYPE=1` to
request the sub-stream. Diagnostics include SDK/login/key/preview status,
decoder errors, and decoded frame counts. The code does not print the AES key
or verification code.

## Licensing and packaging

HCNetSDK and PlayCtrl are proprietary vendor components. Obtain the SDK from
Hikvision and review its license and redistribution terms. This project does
not download, include, or redistribute the SDK binaries. The application
helper is compiled locally against the SDK installation. The Flatpak sandbox
does not automatically have access to arbitrary host SDK directories; use a
native installation or AppImage for this optional backend unless you
explicitly grant the required filesystem access.
