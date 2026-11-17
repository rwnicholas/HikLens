# Standalone Hikvision Linux SDK probe

This probe is separate from `cam_viewer.py`. It targets the official
**Device Network SDK_Linux64 V6.1.11.40**, package build
`20260922_linux64`, for x86-64 Linux.

The package download is listed on Hikvision's [HiTools SDK page](https://www.hikvision.com/en/support/tools/hitools/clf4633a00e385d6ea/).
The source archive is expected at:

```text
~/Downloads/EN-HCNetSDKV6.1.11.40_build20260922_linux64/
```

Build with:

```sh
make -C poc/hikvision-sdk
```

Set credentials in the environment (do not put them in the command history),
then run the test:

```sh
export HIKVISION_HOST=192.168.101.8
export HIKVISION_PORT=8000
export HIKVISION_USERNAME='...'
export HIKVISION_PASSWORD='...'
export HIKVISION_CHANNEL=1
export HIKVISION_RUN_SECONDS=15
make -C poc/hikvision-sdk run
```

The test logs in, makes a read-only `NET_DVR_GET_AES_KEY` request, supplies the
result to `NET_DVR_SetSDKSecretKey`, starts one private-protocol main-stream
preview, and counts decoded PlayCtrl frames. The key is never printed. If the
read-only request is unavailable, an exact 16-byte key can instead be supplied
as 32 hexadecimal characters in `HIKVISION_AES_KEY_HEX`; the test does not
transform or guess how a shorter Verification Code maps to that key.

The test also probes the separate per-player-port `PlayM4_SetSecretKey` API
using `ENCRYPT_AES_10R_VIDEO`, which matches the DVR's reported video
encryption type `2`, and key length `128`. The packaged Linux header confirms
the signature and encryption-type constant but does not document the key-length
unit; treat that argument as an on-device test, not a vendor-guaranteed mapping.
To compare the two plausible length units, set
`HIKVISION_PLAYM4_KEY_LENGTH=16` before running; the default is `128`.
`HIKVISION_PLAYM4_WINDOW` can supply an existing X11 window ID; otherwise the
test passes a null window to PlayCtrl.

The `helper` target builds the same standalone probe as an application-side
frame-pipe helper at
`~/.local/lib/hikvision-camera-viewer/hikvision_stream_helper`. It remains
outside the source tree and has an RPATH to the SDK selected with `SDK_ROOT`.
The helper emits structured status lines to stderr and writes only decoded
RGB32 frames (with a small length-prefixed header) to its inherited frame pipe.
It exits with a decoder error if frames are not produced; it does not emit
black-frame placeholders.

The application helper removes `DISPLAY` and `WAYLAND_DISPLAY` and sets
`EGL_PLATFORM=surfaceless` in its own process only. A 5-second channel-1 test
with no display server verified that this avoids the earlier vendor-renderer
crash while PlayCtrl receives the stream. It still decoded zero frames, so
this confirms headless operation only, not successful decryption. The Qt
application retains its original Wayland/X11 environment.

`NET_DVR_GET_AES_KEY` is documented in the package's General Developer Guide as
an optional `NET_DVR_GetDVRConfig` command (6113) that returns the current
stream AES key in `NET_DVR_AES_KEY_INFO`. The package header declares a
six-argument `NET_DVR_GetDVRConfig`, while the bundled guide's API reference
prints seven arguments (`lRuleID` and `lChannel`). This probe compiles against
the exact package header and tries the documented generic channel values
read-only; it does not call `NET_DVR_InquestSetSecretKey` or
`NET_DVR_InquestStreamEncrypt`, which can change device settings.

The probe reports decoded frame count and dimensions. A successful build or
SDK initialization alone does not establish that the DVR accepted a key or
produced decoded video.

## DVR test result

On the `iDS-7204HQHI-M1/T`, login on SDK port 8000 succeeded. The DVR returned
the 16-byte stream key via `NET_DVR_GET_AES_KEY` with channel argument `-1`, and
`NET_DVR_SetSDKSecretKey` returned success. Channel 1 main-stream preview
delivered data to PlayCtrl without input errors. PlayCtrl reported video
encryption type `2` and `decoder_key_set=1` after `PlayM4_SetSecretKey`.

No decoded frames were received in either tested PlayCtrl key-length variant:
128 (403 chunks, 720336 bytes over 15 seconds) or 16 (135 chunks, 239768 bytes
over 5 seconds). Thus authentication, key retrieval, SDK key configuration,
preview delivery, and PlayCtrl key setup are verified, but successful
decryption/decoding is not. `NET_DVR_SetSDKSecretKey` accepting the retrieved
key does not establish that the Verification Code was supplied or accepted.
Further integration should wait for Hikvision to clarify the documented
`PlayM4_SetSecretKey` length semantics and the correct decoder key source or
verification-code mechanism for this model/firmware.

The application helper was also run headlessly for 15 seconds with
`EGL_PLATFORM=surfaceless`: login, key retrieval, preview, and PlayCtrl setup
succeeded, with 404 chunks / 757476 bytes and zero decoded frames. It emitted
the expected explicit `No decoded frames received within 15 seconds` diagnostic.
