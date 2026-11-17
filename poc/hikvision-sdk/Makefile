SDK_ROOT ?= $(HOME)/Downloads/EN-HCNetSDKV6.1.11.40_build20260922_linux64
BUILD_DIR ?= /tmp/hikvision-sdk-poc-build
CXX ?= c++

SDK_LIB := $(SDK_ROOT)/lib
SDK_COMPONENTS := $(SDK_LIB)/HCNetSDKCom
TARGET := $(BUILD_DIR)/sdk_stream_test
HELPER ?= $(HOME)/.local/lib/hikvision-camera-viewer/hikvision_stream_helper

.PHONY: all run helper clean

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

run: $(TARGET)
	LD_LIBRARY_PATH="$(SDK_LIB):$(SDK_COMPONENTS):$${LD_LIBRARY_PATH:-}" "$(TARGET)"

clean:
	rm -f "$(TARGET)"
