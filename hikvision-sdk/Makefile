SDK_ROOT ?= $(HOME)/Downloads/EN-HCNetSDKV6.1.11.40_build20260922_linux64
BUILD_DIR ?= /tmp/hikvision-sdk-build
CXX ?= c++

SDK_LIB := $(SDK_ROOT)/lib
SDK_COMPONENTS := $(SDK_LIB)/HCNetSDKCom
TARGET := $(BUILD_DIR)/sdk_stream_test
HELPER ?= $(HOME)/.local/lib/hikvision-camera-viewer/hikvision_stream_helper
STUB_DIR := $(BUILD_DIR)/stubs

.PHONY: all run helper portable-helper clean

all: $(TARGET)

helper: $(HELPER)

$(TARGET): sdk_stream_test.cpp
	mkdir -p "$(BUILD_DIR)"
	$(CXX) -std=c++17 -O2 -Wall -Wextra -Werror \
		-isystem "$(SDK_ROOT)/incEn" \
		-isystem "$(SDK_ROOT)/QtDemo/includeCn" \
		"$<" -L"$(SDK_LIB)" \
		-Wl,-rpath,"$(SDK_LIB):$(SDK_COMPONENTS)" \
		-lhcnetsdk -lPlayCtrl -pthread -o "$@"

$(HELPER): sdk_stream_test.cpp
	mkdir -p "$(dir $(HELPER))"
	$(CXX) -std=c++17 -O2 -Wall -Wextra -Werror \
		-isystem "$(SDK_ROOT)/incEn" \
		-isystem "$(SDK_ROOT)/QtDemo/includeCn" \
		"$<" -L"$(SDK_LIB)" \
		-Wl,-rpath,"$(SDK_LIB):$(SDK_COMPONENTS)" \
		-lhcnetsdk -lPlayCtrl -pthread -o "$@"

portable-helper: sdk_stream_test.cpp
	mkdir -p "$(STUB_DIR)" "$(dir $(HELPER))"
	printf '%s\n' \
		'extern "C" {' \
		'void NET_DVR_Init() {}' \
		'void NET_DVR_Cleanup() {}' \
		'void NET_DVR_GetLastError() {}' \
		'void NET_DVR_SetLogToFile() {}' \
		'void NET_DVR_SetConnectTime() {}' \
		'void NET_DVR_SetReconnect() {}' \
		'void NET_DVR_Login_V40() {}' \
		'void NET_DVR_Logout() {}' \
		'void NET_DVR_GetDVRConfig() {}' \
		'void NET_DVR_SetSDKSecretKey() {}' \
		'void NET_DVR_RealPlay_V40() {}' \
		'void NET_DVR_StopRealPlay() {}' \
		'}' | $(CXX) -x c++ -shared -fPIC -Wl,-soname,libhcnetsdk.so - -o "$(STUB_DIR)/libhcnetsdk.so"
	printf '%s\n' \
		'extern "C" {' \
		'void PlayM4_GetPort() {}' \
		'void PlayM4_FreePort() {}' \
		'void PlayM4_GetLastError() {}' \
		'void PlayM4_SetStreamOpenMode() {}' \
		'void PlayM4_SetSecretKey() {}' \
		'void PlayM4_SetEncryptTypeCallBack() {}' \
		'void PlayM4_OpenStream() {}' \
		'void PlayM4_SetDecodeFrameType() {}' \
		'void PlayM4_SetDecCallBackExMend() {}' \
		'void PlayM4_Play() {}' \
		'void PlayM4_InputData() {}' \
		'void PlayM4_Stop() {}' \
		'void PlayM4_CloseStream() {}' \
		'}' | $(CXX) -x c++ -shared -fPIC -Wl,-soname,libPlayCtrl.so - -o "$(STUB_DIR)/libPlayCtrl.so"
	$(CXX) -std=c++17 -O2 -Wall -Wextra -Werror \
		sdk_stream_test.cpp -L"$(STUB_DIR)" \
		-Wl,--no-as-needed -lhcnetsdk -lPlayCtrl -pthread -o "$(HELPER)"
	rm -rf "$(STUB_DIR)"

run: $(TARGET)
	LD_LIBRARY_PATH="$(SDK_LIB):$(SDK_COMPONENTS):$${LD_LIBRARY_PATH:-}" "$(TARGET)"

clean:
	rm -f "$(TARGET)"
