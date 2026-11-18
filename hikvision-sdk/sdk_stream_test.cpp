#if __has_include(<HCNetSDK.h>)
#include <HCNetSDK.h>
#else
#include <cstdint>

#define CALLBACK
#ifndef TRUE
#define TRUE 1
#endif
#ifndef FALSE
#define FALSE 0
#endif

using DWORD = unsigned int;
using LONG = int;
using WORD = unsigned short;
using BYTE = unsigned char;
using BOOL = int;
using HWND = unsigned int;

constexpr int NET_SDK_MAX_VERIFICATION_CODE_LEN = 32;
constexpr int CARDNUM_LEN_OUT = 32;
constexpr int GUID_LEN = 16;
constexpr int STREAM_ID_LEN = 32;
constexpr DWORD NET_DVR_GET_AES_KEY = 6113;
constexpr DWORD NET_DVR_SYSHEAD = 1;
constexpr DWORD NET_DVR_STREAMDATA = 2;
constexpr DWORD NET_DVR_AUDIOSTREAMDATA = 3;

constexpr LONG NET_DVR_FILE_SUCCESS = 1000;
constexpr LONG NET_DVR_FILE_NOFIND = 1001;
constexpr LONG NET_DVR_ISFINDING = 1002;
constexpr LONG NET_DVR_NOMOREFILE = 1003;
constexpr LONG NET_DVR_FILE_EXCEPTION = 1004;

constexpr DWORD NET_DVR_PLAYSTART = 1;
constexpr DWORD NET_DVR_PLAYPAUSE = 3;
constexpr DWORD NET_DVR_PLAYRESTART = 4;
constexpr DWORD NET_DVR_PLAYFAST = 5;
constexpr DWORD NET_DVR_PLAYSLOW = 6;
constexpr DWORD NET_DVR_PLAYNORMAL = 7;
constexpr DWORD NET_DVR_PLAYSETPOS = 12;
constexpr DWORD NET_DVR_PLAYGETPOS = 13;

struct NET_DVR_DEVICEINFO_V40 {
    BYTE byRes[344];
};

using fLoginResultCallBack = void (*)(LONG lUserID, DWORD dwResult,
                                      NET_DVR_DEVICEINFO_V40* lpDeviceInfo,
                                      void* pUser);

struct NET_DVR_USER_LOGIN_INFO {
    char sDeviceAddress[129];
    BYTE byUseTransport;
    WORD wPort;
    char sUserName[64];
    char sPassword[64];
    fLoginResultCallBack cbLoginResult;
    void* pUser;
    BOOL bUseAsynLogin;
    BYTE byRes3[132];
};

struct NET_DVR_AES_KEY_INFO {
    char sAESKey[16];
    BYTE byRes[64];
};

struct NET_DVR_PREVIEWINFO {
    LONG lChannel;
    DWORD dwStreamType;
    DWORD dwLinkMode;
    HWND hPlayWnd;
    DWORD bBlocked;
    DWORD bPassbackRecord;
    BYTE byPreviewMode;
    BYTE byStreamID[STREAM_ID_LEN];
    BYTE byProtoType;
    BYTE byRes1;
    BYTE byVideoCodingType;
    DWORD dwDisplayBufNum;
    BYTE byNPQMode;
    BYTE byRecvMetaData;
    BYTE byDataType;
    BYTE byReconnect;
    BYTE byRes[212];
};

struct NET_DVR_TIME {
    DWORD dwYear;
    DWORD dwMonth;
    DWORD dwDay;
    DWORD dwHour;
    DWORD dwMinute;
    DWORD dwSecond;
};

struct NET_DVR_SPECIAL_FINDINFO_UNION {
    BYTE byLenth[8];
};

struct NET_DVR_FILECOND_V40 {
    LONG lChannel;
    DWORD dwFileType;
    DWORD dwIsLocked;
    DWORD dwUseCardNo;
    BYTE sCardNumber[CARDNUM_LEN_OUT];
    NET_DVR_TIME struStartTime;
    NET_DVR_TIME struStopTime;
    BYTE byDrawFrame;
    BYTE byFindType;
    BYTE byQuickSearch;
    BYTE bySpecialFindInfoType;
    DWORD dwVolumeNum;
    BYTE byWorkingDeviceGUID[GUID_LEN];
    NET_DVR_SPECIAL_FINDINFO_UNION uSpecialFindInfo;
    BYTE byStreamType;
    BYTE byAudioFile;
    BYTE byRes2[30];
};

struct NET_DVR_FINDDATA_V40 {
    char sFileName[100];
    NET_DVR_TIME struStartTime;
    NET_DVR_TIME struStopTime;
    DWORD dwFileSize;
    char sCardNum[32];
    BYTE byLocked;
    BYTE byFileType;
    BYTE byQuickSearch;
    BYTE byRes;
    DWORD dwFileIndex;
    BYTE byStreamType;
    BYTE byRes1[127];
};

struct NET_DVR_STREAM_INFO {
    DWORD dwSize;
    BYTE byID[STREAM_ID_LEN];
    DWORD dwChannel;
    BYTE byRes[32];
};

struct NET_DVR_VOD_PARA {
    DWORD dwSize;
    NET_DVR_STREAM_INFO struIDInfo;
    NET_DVR_TIME struBeginTime;
    NET_DVR_TIME struEndTime;
    HWND hWnd;
    BYTE byDrawFrame;
    BYTE byVolumeType;
    BYTE byVolumeNum;
    BYTE byStreamType;
    DWORD dwFileIndex;
    BYTE byAudioFile;
    BYTE byCourseFile;
    BYTE byDownload;
    BYTE byOptimalStreamType;
    BYTE byUseAsyn;
    BYTE byRes2[19];
};

static_assert(sizeof(NET_DVR_DEVICEINFO_V40) == 344);
static_assert(sizeof(NET_DVR_AES_KEY_INFO) == 80);
static_assert(sizeof(NET_DVR_PREVIEWINFO) == 280);
static_assert(sizeof(NET_DVR_TIME) == 24);
static_assert(sizeof(NET_DVR_FILECOND_V40) == 160);
static_assert(sizeof(NET_DVR_FINDDATA_V40) == 320);
static_assert(sizeof(NET_DVR_STREAM_INFO) == 72);
static_assert(sizeof(NET_DVR_VOD_PARA) == 160);

using REALDATACALLBACK = void (*)(LONG lRealHandle, DWORD dwDataType,
                                  BYTE* pBuffer, DWORD dwBufSize, void* pUser);

extern "C" {
BOOL NET_DVR_Init();
BOOL NET_DVR_Cleanup();
DWORD NET_DVR_GetLastError();
BOOL NET_DVR_SetLogToFile(DWORD nLogLevel, char* strLogDir, BOOL bAutoDel);
BOOL NET_DVR_SetConnectTime(DWORD dwWaitTime, DWORD dwTryTimes);
BOOL NET_DVR_SetReconnect(DWORD dwInterval, BOOL bEnableRecon);
LONG NET_DVR_Login_V40(NET_DVR_USER_LOGIN_INFO* pLoginInfo,
                       NET_DVR_DEVICEINFO_V40* lpDeviceInfo);
BOOL NET_DVR_Logout(LONG lUserID);
BOOL NET_DVR_GetDVRConfig(LONG lUserID, DWORD dwCommand, LONG lChannel,
                          void* lpOutBuffer, DWORD dwOutBufferSize,
                          DWORD* lpBytesReturned);
BOOL NET_DVR_SetSDKSecretKey(LONG lUserID, char* pSecretKey);
LONG NET_DVR_RealPlay_V40(LONG lUserID, NET_DVR_PREVIEWINFO* lpPreviewInfo,
                          REALDATACALLBACK fRealDataCallBack_V30, void* pUser);
BOOL NET_DVR_StopRealPlay(LONG lRealHandle);
LONG NET_DVR_FindFile_V40(LONG lUserID, NET_DVR_FILECOND_V40* pFindCond);
LONG NET_DVR_FindNextFile_V40(LONG lFindHandle,
                              NET_DVR_FINDDATA_V40* lpFindData);
BOOL NET_DVR_FindClose_V30(LONG lFindHandle);
LONG NET_DVR_PlayBackByName(LONG lUserID, char* sPlayBackFileName, HWND hWnd);
LONG NET_DVR_PlayBackByTime_V40(LONG lUserID,
                                const NET_DVR_VOD_PARA* pVodPara);
BOOL NET_DVR_SetPlayDataCallBack_V40(LONG lPlayHandle,
                                     REALDATACALLBACK fPlayDataCallBack_V40,
                                     void* pUser);
BOOL NET_DVR_PlayBackControl_V40(LONG lPlayHandle, DWORD dwControlCode,
                                 void* lpInBuffer, DWORD dwInLen,
                                 void* lpOutBuffer, DWORD* lpOutLen);
BOOL NET_DVR_GetPlayBackOsdTime(LONG lPlayHandle, NET_DVR_TIME* lpOsdTime);
BOOL NET_DVR_StopPlayBack(LONG lPlayHandle);
}
#endif

#if __has_include(<LinuxPlayM4.h>)
#include <LinuxPlayM4.h>
#else
using PLAYM4_HWND = unsigned int;

constexpr unsigned int STREAME_REALTIME = 0;
constexpr unsigned int STREAME_FILE = 1;
constexpr int ENCRYPT_AES_10R_VIDEO = 2;
constexpr int T_YV12 = 3;
constexpr int T_RGB32 = 7;
constexpr unsigned int PLAYM4_BUF_OVER = 11;

struct ENCRYPT_INFO {
    long nVideoEncryptType;
    long nAudioEncryptType;
    long nSetSecretKey;
};

struct FRAME_INFO {
    int nWidth;
    int nHeight;
    int nStamp;
    int nType;
    int nFrameRate;
    unsigned int dwFrameNum;
};

extern "C" {
int PlayM4_GetPort(int* nPort);
int PlayM4_FreePort(int nPort);
unsigned int PlayM4_GetLastError(int nPort);
int PlayM4_SetStreamOpenMode(int nPort, unsigned int nMode);
int PlayM4_SetSecretKey(int nPort, int lKeyType, char* pSecretKey, int lKeyLen);
int PlayM4_SetEncryptTypeCallBack(
    int nPort, unsigned int nType,
    void (*EncryptTypeCBFun)(int, ENCRYPT_INFO*, void*, int), void* nUser);
int PlayM4_OpenStream(int nPort, unsigned char* pFileHeadBuf,
                      unsigned int nSize, unsigned int nBufPoolSize);
int PlayM4_SetDecodeFrameType(int nPort, unsigned int nFrameType);
int PlayM4_SetDecCallBackExMend(
    int nPort, void (*DecCBFun)(int, char*, int, FRAME_INFO*, void*, int),
    char* pDest, int nDestSize, void* nUser);
int PlayM4_Play(int nPort, PLAYM4_HWND hWnd);
int PlayM4_Fast(int nPort);
int PlayM4_Slow(int nPort);
int PlayM4_InputData(int nPort, unsigned char* pBuf, unsigned int nSize);
int PlayM4_Stop(int nPort);
int PlayM4_CloseStream(int nPort);
}
#endif

#ifndef STREAME_FILE
#define STREAME_FILE 1
#endif
#ifndef PLAYM4_BUF_OVER
#define PLAYM4_BUF_OVER 11
#endif

#include <algorithm>
#include <array>
#include <atomic>
#include <charconv>
#include <chrono>
#include <csignal>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <iostream>
#include <mutex>
#include <string>
#include <string_view>
#include <thread>
#include <unistd.h>
#include <vector>

namespace {

volatile std::sig_atomic_t g_keep_running = 1;
std::mutex g_diagnostics_mutex;

void handle_signal(int) {
    g_keep_running = 0;
}

struct TestState {
    std::array<char, NET_SDK_MAX_VERIFICATION_CODE_LEN + 1>
        stream_verification_code{};
    int player_key_length{128};
    int frame_output_fd{-1};
    int target_fps{10};
    int stream_type{0};
    int playback_speed_steps{0};
    bool playback_mode{false};
    std::mutex frame_output_mutex;
    std::chrono::steady_clock::time_point last_output_time{};
    std::atomic<int> player_port{-1};
    std::atomic<int> player_error{0};
    std::atomic<unsigned int> player_error_code{0};
    std::atomic<int> sdk_init_status{0};
    std::atomic<int> login_status{0};
    std::atomic<int> aes_key_status{0};
    std::atomic<int> sdk_key_status{0};
    std::atomic<int> preview_status{0};
    std::atomic<int> playctrl_status{0};
    std::atomic<int> decoder_key_status{0};
    std::atomic<bool> stream_verification_code_configured{false};
    std::atomic<bool> stream_verification_code_applied{false};
    std::atomic<unsigned int> sdk_error_code{0};
    std::atomic<int> decoder_error_code{0};
    std::atomic<int> playback_progress{-1};
    std::mutex osd_time_mutex;
    std::string playback_osd_time;
    std::atomic<std::uint64_t> decoded_frames{0};
    std::atomic<std::uint64_t> system_headers{0};
    std::atomic<std::uint64_t> stream_chunks{0};
    std::atomic<std::uint64_t> stream_bytes{0};
    std::atomic<std::uint64_t> input_failures{0};
    std::atomic<int> width{0};
    std::atomic<int> height{0};
    std::atomic<int> decoded_frame_type{-1};
    std::atomic<int> decoded_frame_bytes{0};
    std::atomic<std::uint64_t> frames_sent{0};
    std::atomic<bool> encrypt_info_seen{false};
    std::atomic<long> video_encrypt_type{-1};
    std::atomic<long> audio_encrypt_type{-1};
    std::atomic<long> decoder_key_set{-1};
    PLAYM4_HWND play_window{0};
};

const char* status_name(int status) {
    if (status < 0) {
        return "failed";
    }
    return status == 1 ? "ok" : "pending";
}

const char* decoder_error_name(int error) {
    switch (error) {
        case 1:
            return "PlayM4_GetPort failed";
        case 2:
            return "PlayM4_SetStreamOpenMode failed";
        case 3:
            return "PlayM4_SetSecretKey failed";
        case 4:
            return "PlayM4_SetEncryptTypeCallBack failed";
        case 5:
            return "PlayM4_OpenStream failed";
        case 6:
            return "PlayM4_SetDecCallBackExMend failed";
        case 7:
            return "PlayM4_Play failed";
        case 8:
            return "PlayM4_InputData failed";
        case 9:
            return "No decoded frames received within 15 seconds";
        case 10:
            return "PlayCtrl returned an unsupported decoded frame format";
        case 11:
            return "Could not write a decoded frame to the application";
        case 12:
            return "PlayM4_SetDecodeFrameType failed";
        case 13:
            return "Streaming Verification Code is required";
        case 14:
            return "Streaming Verification Code exceeds the SDK limit";
        default:
            return "";
    }
}

void emit_diagnostics(TestState& state, bool helper_mode) {
    if (!helper_mode) {
        return;
    }
    std::string osd_time;
    {
        std::lock_guard<std::mutex> osd_lock(state.osd_time_mutex);
        osd_time = state.playback_osd_time;
    }
    std::lock_guard<std::mutex> lock(g_diagnostics_mutex);
    std::cerr << "HIKVISION_DIAGNOSTIC {"
              << "\"sdk_init\":\"" << status_name(state.sdk_init_status.load())
              << "\",\"login\":\"" << status_name(state.login_status.load())
              << "\",\"aes_key_retrieval\":\""
              << status_name(state.aes_key_status.load())
              << "\",\"sdk_secret_key\":\""
              << status_name(state.sdk_key_status.load())
              << "\",\"preview\":\""
              << status_name(state.preview_status.load())
              << "\",\"stream_type\":" << state.stream_type
              << ",\"encryption_type\":"
              << state.video_encrypt_type.load()
              << ",\"playctrl_initialization\":\""
              << status_name(state.playctrl_status.load())
              << "\",\"stream_chunks\":" << state.stream_chunks.load()
              << ",\"stream_bytes\":" << state.stream_bytes.load()
              << ",\"decoder_key_configuration\":\""
              << status_name(state.decoder_key_status.load())
              << "\",\"decoder_key_set\":"
              << state.decoder_key_set.load()
              << ",\"stream_verification_code_configured\":"
              << (state.stream_verification_code_configured.load()
                      ? "true"
                      : "false")
              << ",\"stream_verification_code_applied\":"
              << (state.stream_verification_code_applied.load() ? "true"
                                                                 : "false")
              << ",\"frames_decoded\":" << state.decoded_frames.load()
              << ",\"frames_sent\":" << state.frames_sent.load()
              << ",\"input_failures\":" << state.input_failures.load()
              << ",\"frame_width\":" << state.width.load()
              << ",\"frame_height\":" << state.height.load()
              << ",\"decoded_frame_type\":"
              << state.decoded_frame_type.load()
              << ",\"decoded_frame_bytes\":"
              << state.decoded_frame_bytes.load()
              << ",\"playback_progress\":"
              << state.playback_progress.load()
              << ",\"playback_osd_time\":\"" << osd_time << "\""
              << ",\"sdk_error_code\":" << state.sdk_error_code.load()
              << ",\"playctrl_error_code\":"
              << state.player_error_code.load()
              << ",\"decoder_error\":\""
              << decoder_error_name(state.decoder_error_code.load())
              << "\"}" << std::endl;
}

std::string env_or(const char* name, const char* fallback = "") {
    const char* value = std::getenv(name);
    return value == nullptr ? fallback : value;
}

bool parse_integer(const char* name, long minimum, long maximum, long fallback,
                   long& result) {
    const char* value = std::getenv(name);
    if (value == nullptr || *value == '\0') {
        result = fallback;
        return true;
    }

    const std::string_view text(value);
    const auto parsed =
        std::from_chars(text.data(), text.data() + text.size(), result);
    return parsed.ec == std::errc{} && parsed.ptr == text.data() + text.size() &&
           result >= minimum && result <= maximum;
}

template <std::size_t N>
bool copy_field(char (&destination)[N], const std::string& value) {
    if (value.empty() || value.size() >= N) {
        return false;
    }
    std::memcpy(destination, value.data(), value.size());
    destination[value.size()] = '\0';
    return true;
}

template <std::size_t N>
bool copy_field(std::array<char, N>& destination, const std::string& value) {
    if (value.empty() || value.size() >= N) {
        return false;
    }
    std::memcpy(destination.data(), value.data(), value.size());
    destination[value.size()] = '\0';
    return true;
}

bool parse_number_slice(std::string_view slice, unsigned int minimum,
                        unsigned int maximum, DWORD& out) {
    unsigned int value = 0;
    const auto parsed =
        std::from_chars(slice.data(), slice.data() + slice.size(), value);
    if (parsed.ec != std::errc{} ||
        parsed.ptr != slice.data() + slice.size() || value < minimum ||
        value > maximum) {
        return false;
    }
    out = static_cast<DWORD>(value);
    return true;
}

bool parse_dvr_time(std::string_view text, NET_DVR_TIME& out) {
    if (text.size() != 19 || text[4] != '-' || text[7] != '-' ||
        (text[10] != ' ' && text[10] != 'T') || text[13] != ':' ||
        text[16] != ':') {
        return false;
    }
    return parse_number_slice(text.substr(0, 4), 1970, 2099, out.dwYear) &&
           parse_number_slice(text.substr(5, 2), 1, 12, out.dwMonth) &&
           parse_number_slice(text.substr(8, 2), 1, 31, out.dwDay) &&
           parse_number_slice(text.substr(11, 2), 0, 23, out.dwHour) &&
           parse_number_slice(text.substr(14, 2), 0, 59, out.dwMinute) &&
           parse_number_slice(text.substr(17, 2), 0, 59, out.dwSecond);
}

std::string format_dvr_time(const NET_DVR_TIME& t) {
    char buffer[32]{};
    std::snprintf(buffer, sizeof(buffer), "%04u-%02u-%02u %02u:%02u:%02u",
                  t.dwYear, t.dwMonth, t.dwDay, t.dwHour, t.dwMinute,
                  t.dwSecond);
    return buffer;
}

std::string json_escape(std::string_view text) {
    std::string escaped;
    escaped.reserve(text.size());
    for (const unsigned char ch : text) {
        switch (ch) {
            case '\"':
                escaped += "\\\"";
                break;
            case '\\':
                escaped += "\\\\";
                break;
            case '\n':
                escaped += "\\n";
                break;
            case '\r':
                escaped += "\\r";
                break;
            case '\t':
                escaped += "\\t";
                break;
            default:
                if (ch >= 0x20) {
                    escaped.push_back(static_cast<char>(ch));
                }
                break;
        }
    }
    return escaped;
}

int hex_value(char value) {
    if (value >= '0' && value <= '9') {
        return value - '0';
    }
    if (value >= 'a' && value <= 'f') {
        return value - 'a' + 10;
    }
    if (value >= 'A' && value <= 'F') {
        return value - 'A' + 10;
    }
    return -1;
}

bool parse_key_hex(const std::string& text, std::array<char, 16>& key) {
    if (text.size() != key.size() * 2) {
        return false;
    }
    for (std::size_t index = 0; index < key.size(); ++index) {
        const int high = hex_value(text[index * 2]);
        const int low = hex_value(text[index * 2 + 1]);
        if (high < 0 || low < 0) {
            return false;
        }
        key[index] = static_cast<char>((high << 4) | low);
    }
    return true;
}

bool get_stream_key(LONG user_id, std::array<char, 16>& key,
                    std::string& source) {
    constexpr std::array<LONG, 3> channel_candidates{-1, 0, 1};
    DWORD last_error = 0;
    for (const LONG channel : channel_candidates) {
        NET_DVR_AES_KEY_INFO key_info{};
        DWORD bytes_returned = 0;
        if (NET_DVR_GetDVRConfig(user_id, NET_DVR_GET_AES_KEY, channel,
                                 &key_info, sizeof(key_info), &bytes_returned)) {
            if (bytes_returned < key.size()) {
                std::cerr << "NET_DVR_GET_AES_KEY returned only "
                          << bytes_returned << " bytes\n";
                return false;
            }
            std::memcpy(key.data(), key_info.sAESKey, key.size());
            source = "NET_DVR_GET_AES_KEY";
            std::cout << "AES key retrieved with channel argument " << channel
                      << " (value withheld)\n";
            return true;
        }
        last_error = NET_DVR_GetLastError();
    }

    const std::string key_hex = env_or("HIKVISION_AES_KEY_HEX");
    if (!key_hex.empty() && parse_key_hex(key_hex, key)) {
        source = "HIKVISION_AES_KEY_HEX";
        std::cout << "Using supplied 16-byte AES key (value withheld)\n";
        return true;
    }

    std::cerr << "Could not retrieve the stream key with NET_DVR_GET_AES_KEY "
                 "(last SDK error "
              << last_error
              << "); set HIKVISION_AES_KEY_HEX to exactly 32 hex characters "
                 "if you have the raw 16-byte key\n";
    return false;
}

void set_player_error(TestState* state, int error, int port = -1) {
    int expected = 0;
    if (state->player_error.compare_exchange_strong(expected, error)) {
        if (port >= 0) {
            state->player_error_code.store(PlayM4_GetLastError(port));
        }
        state->playctrl_status.store(-1);
        if (error == 3) {
            state->decoder_key_status.store(-1);
        }
        state->decoder_error_code.store(error);
    }
}

void CALLBACK encrypt_type_callback(int, ENCRYPT_INFO* info, void* user,
                                    int) {
    if (info == nullptr || user == nullptr) {
        return;
    }
    auto* state = static_cast<TestState*>(user);
    state->video_encrypt_type.store(info->nVideoEncryptType);
    state->audio_encrypt_type.store(info->nAudioEncryptType);
    state->decoder_key_set.store(info->nSetSecretKey);
    state->encrypt_info_seen.store(true);
}

bool write_all(int fd, const void* data, std::size_t size) {
    const auto* bytes = static_cast<const char*>(data);
    while (size > 0) {
        const ssize_t written = ::write(fd, bytes, size);
        if (written < 0) {
            if (errno == EINTR) {
                continue;
            }
            return false;
        }
        bytes += written;
        size -= static_cast<std::size_t>(written);
    }
    return true;
}

bool convert_yv12_to_rgb32(const char* source, int width, int height,
                           int source_size, std::vector<char>& destination) {
    if (source == nullptr || width < 2 || height < 2 ||
        width % 2 != 0 || height % 2 != 0) {
        return false;
    }

    const std::size_t pixel_count =
        static_cast<std::size_t>(width) * static_cast<std::size_t>(height);
    const std::size_t chroma_size = pixel_count / 4;
    if (pixel_count + chroma_size * 2 !=
        static_cast<std::size_t>(source_size)) {
        return false;
    }

    try {
        destination.resize(pixel_count * 4);
    } catch (const std::bad_alloc&) {
        return false;
    }

    const auto clamp = [](int value) {
        return std::clamp(value, 0, 255);
    };
    const auto* y_plane = reinterpret_cast<const unsigned char*>(source);
    const auto* v_plane = y_plane + pixel_count;
    const auto* u_plane = v_plane + chroma_size;
    auto* rgb = reinterpret_cast<unsigned char*>(destination.data());

    for (int y = 0; y < height; ++y) {
        for (int x = 0; x < width; ++x) {
            const std::size_t pixel =
                static_cast<std::size_t>(y) * width + x;
            const std::size_t chroma =
                static_cast<std::size_t>(y / 2) * (width / 2) + x / 2;
            const int luminance = std::max(0, static_cast<int>(y_plane[pixel]) - 16);
            const int v = static_cast<int>(v_plane[chroma]) - 128;
            const int u = static_cast<int>(u_plane[chroma]) - 128;
            const int red = clamp((298 * luminance + 409 * v + 128) >> 8);
            const int green =
                clamp((298 * luminance - 100 * u - 208 * v + 128) >> 8);
            const int blue = clamp((298 * luminance + 516 * u + 128) >> 8);
            const std::size_t output = pixel * 4;
            rgb[output] = static_cast<unsigned char>(blue);
            rgb[output + 1] = static_cast<unsigned char>(green);
            rgb[output + 2] = static_cast<unsigned char>(red);
            rgb[output + 3] = 0xff;
        }
    }
    return true;
}

void CALLBACK decoded_frame_callback(int, char* buffer, int size,
                                     FRAME_INFO* frame_info,
                                     void* user, int) {
    if (frame_info == nullptr || user == nullptr || buffer == nullptr ||
        size <= 0) {
        return;
    }
    auto* state = static_cast<TestState*>(user);
    state->width.store(frame_info->nWidth);
    state->height.store(frame_info->nHeight);
    state->decoded_frame_type.store(frame_info->nType);
    state->decoded_frame_bytes.store(size);
    state->decoded_frames.fetch_add(1);

    if (state->frame_output_fd >= 0) {
        const std::uint64_t pixel_count =
            static_cast<std::uint64_t>(frame_info->nWidth) *
            static_cast<std::uint64_t>(frame_info->nHeight);
        const std::uint64_t rgb_size = pixel_count * 4U;
        std::vector<char> converted;
        const char* output = buffer;
        if (frame_info->nType == T_YV12) {
            if (!convert_yv12_to_rgb32(buffer, frame_info->nWidth,
                                       frame_info->nHeight, size, converted)) {
                state->decoder_error_code.store(10);
                return;
            }
            output = converted.data();
        } else if (frame_info->nType != T_RGB32 ||
                   rgb_size != static_cast<std::uint64_t>(size)) {
            state->decoder_error_code.store(10);
            return;
        }
        std::lock_guard<std::mutex> lock(state->frame_output_mutex);
        const auto now = std::chrono::steady_clock::now();
        const auto interval = std::chrono::milliseconds(
            std::max(1, 1000 / state->target_fps));
        if (state->last_output_time.time_since_epoch().count() != 0 &&
            now - state->last_output_time < interval) {
            return;
        }
        state->last_output_time = now;
        struct FrameHeader {
            char magic[4];
            std::uint32_t width;
            std::uint32_t height;
            std::uint32_t size;
        };
        static_assert(sizeof(FrameHeader) == 16);
        const FrameHeader header{{'H', 'I', 'K', 'F'},
                                 static_cast<std::uint32_t>(frame_info->nWidth),
                                 static_cast<std::uint32_t>(frame_info->nHeight),
                                 static_cast<std::uint32_t>(rgb_size)};
        if (!write_all(state->frame_output_fd, &header, sizeof(header)) ||
            !write_all(state->frame_output_fd, output,
                       static_cast<std::size_t>(rgb_size))) {
            state->decoder_error_code.store(11);
            return;
        }
        state->frames_sent.fetch_add(1);
    }
}

void CALLBACK stream_callback(LONG, DWORD data_type, BYTE* buffer,
                              DWORD size, void* user) {
    if (user == nullptr || buffer == nullptr || size == 0) {
        return;
    }
    auto* state = static_cast<TestState*>(user);

    if (data_type == NET_DVR_SYSHEAD) {
        state->system_headers.fetch_add(1);
        if (state->player_port.load() >= 0 || state->player_error.load() != 0) {
            return;
        }

        int port = -1;
        if (!PlayM4_GetPort(&port)) {
            set_player_error(state, 1);
            return;
        }
        const unsigned int open_mode =
            state->playback_mode ? STREAME_FILE : STREAME_REALTIME;
        if (!PlayM4_SetStreamOpenMode(port, open_mode)) {
            set_player_error(state, 2, port);
            PlayM4_FreePort(port);
            return;
        }
        if (state->stream_verification_code_configured.load()) {
            if (!PlayM4_SetSecretKey(port, ENCRYPT_AES_10R_VIDEO,
                                     state->stream_verification_code.data(),
                                     state->player_key_length)) {
                set_player_error(state, 3, port);
                PlayM4_FreePort(port);
                return;
            }
            state->decoder_key_status.store(1);
            state->stream_verification_code_applied.store(true);
        }
        if (!PlayM4_SetEncryptTypeCallBack(
                port, 1, encrypt_type_callback, state)) {
            set_player_error(state, 4, port);
            PlayM4_FreePort(port);
            return;
        }
        if (!PlayM4_OpenStream(port, buffer, size, 4U * 1024U * 1024U)) {
            set_player_error(state, 5, port);
            PlayM4_FreePort(port);
            return;
        }
        if (!PlayM4_SetDecodeFrameType(port, T_RGB32)) {
            set_player_error(state, 12, port);
            PlayM4_CloseStream(port);
            PlayM4_FreePort(port);
            return;
        }
        if (!PlayM4_SetDecCallBackExMend(
                port, decoded_frame_callback, nullptr, 0, state)) {
            set_player_error(state, 6, port);
            PlayM4_CloseStream(port);
            PlayM4_FreePort(port);
            return;
        }
        state->player_port.store(port);
        if (!PlayM4_Play(port, state->play_window)) {
            set_player_error(state, 7, port);
            state->player_port.store(-1);
            PlayM4_CloseStream(port);
            PlayM4_FreePort(port);
        } else {
            if (state->playback_mode) {
                for (int step = 0; step < state->playback_speed_steps; ++step) {
                    PlayM4_Fast(port);
                }
                for (int step = 0; step > state->playback_speed_steps; --step) {
                    PlayM4_Slow(port);
                }
            }
            state->playctrl_status.store(1);
        }
        return;
    }

    const int port = state->player_port.load();
    if (port < 0 || state->player_error.load() != 0) {
        return;
    }
    if (data_type == NET_DVR_STREAMDATA ||
        data_type == NET_DVR_AUDIOSTREAMDATA) {
        state->stream_chunks.fetch_add(1);
        state->stream_bytes.fetch_add(size);
        bool input_ok = PlayM4_InputData(port, buffer, size) != 0;
        if (!input_ok && state->playback_mode) {
            for (int retry = 0;
                 retry < 500 && g_keep_running &&
                 PlayM4_GetLastError(port) == PLAYM4_BUF_OVER;
                 ++retry) {
                std::this_thread::sleep_for(std::chrono::milliseconds(10));
                if (PlayM4_InputData(port, buffer, size)) {
                    input_ok = true;
                    break;
                }
            }
        }
        if (!input_ok) {
            state->input_failures.fetch_add(1);
            set_player_error(state, 8, port);
        }
    }
}

int list_recordings() {
    const std::string host = env_or("HIKVISION_HOST", "192.168.101.8");
    const std::string username = env_or("HIKVISION_USERNAME");
    const std::string password = env_or("HIKVISION_PASSWORD");
    const std::string start_text = env_or("HIKVISION_START_TIME");
    const std::string end_text = env_or("HIKVISION_END_TIME");
    long port = 8000;
    long channel = 1;
    NET_DVR_TIME start_time{};
    NET_DVR_TIME end_time{};
    if (username.empty() || password.empty()) {
        std::cerr << "Set HIKVISION_USERNAME and HIKVISION_PASSWORD\n";
        return 2;
    }
    if (!parse_integer("HIKVISION_PORT", 1, 65535, 8000, port) ||
        !parse_integer("HIKVISION_CHANNEL", 1, 256, 1, channel) ||
        !parse_dvr_time(start_text, start_time) ||
        !parse_dvr_time(end_text, end_time)) {
        std::cerr << "Invalid recording search parameters\n";
        return 2;
    }

    NET_DVR_SetLogToFile(0, nullptr, TRUE);
    if (!NET_DVR_Init()) {
        std::cerr << "NET_DVR_Init failed: " << NET_DVR_GetLastError() << '\n';
        return 3;
    }
    NET_DVR_SetConnectTime(5000, 3);
    NET_DVR_SetReconnect(10000, TRUE);

    NET_DVR_USER_LOGIN_INFO login_info{};
    NET_DVR_DEVICEINFO_V40 device_info{};
    if (!copy_field(login_info.sDeviceAddress, host) ||
        !copy_field(login_info.sUserName, username) ||
        !copy_field(login_info.sPassword, password)) {
        std::cerr << "Host or credential exceeds the SDK field size\n";
        NET_DVR_Cleanup();
        return 2;
    }
    login_info.wPort = static_cast<WORD>(port);
    login_info.bUseAsynLogin = FALSE;

    const LONG user_id = NET_DVR_Login_V40(&login_info, &device_info);
    if (user_id < 0) {
        std::cerr << "NET_DVR_Login_V40 failed: " << NET_DVR_GetLastError()
                  << '\n';
        NET_DVR_Cleanup();
        return 4;
    }

    NET_DVR_FILECOND_V40 file_cond{};
    file_cond.lChannel = static_cast<LONG>(channel);
    file_cond.dwFileType = 0xff;
    file_cond.dwIsLocked = 0xff;
    file_cond.dwUseCardNo = 0;
    file_cond.struStartTime = start_time;
    file_cond.struStopTime = end_time;

    const LONG find_handle = NET_DVR_FindFile_V40(user_id, &file_cond);
    if (find_handle < 0) {
        std::cerr << "NET_DVR_FindFile_V40 failed: " << NET_DVR_GetLastError()
                  << '\n';
        NET_DVR_Logout(user_id);
        NET_DVR_Cleanup();
        return 12;
    }

    int exit_code = 0;
    const auto search_start = std::chrono::steady_clock::now();
    while (g_keep_running) {
        NET_DVR_FINDDATA_V40 file_data{};
        const LONG status = NET_DVR_FindNextFile_V40(find_handle, &file_data);
        if (status == NET_DVR_ISFINDING) {
            if (std::chrono::steady_clock::now() - search_start >=
                std::chrono::seconds(30)) {
                std::cerr << "NET_DVR_FindNextFile_V40 timed out\n";
                exit_code = 12;
                break;
            }
            std::this_thread::sleep_for(std::chrono::milliseconds(20));
            continue;
        }
        if (status == NET_DVR_FILE_SUCCESS) {
            const std::size_t name_len =
                strnlen(file_data.sFileName, sizeof(file_data.sFileName));
            const std::string_view file_name(file_data.sFileName, name_len);
            std::cout << "HIKVISION_RECORDING {"
                      << "\"name\":\"" << json_escape(file_name) << "\","
                      << "\"channel\":" << channel << ","
                      << "\"start_time\":\""
                      << format_dvr_time(file_data.struStartTime) << "\","
                      << "\"end_time\":\""
                      << format_dvr_time(file_data.struStopTime) << "\","
                      << "\"size_bytes\":" << file_data.dwFileSize << ","
                      << "\"file_type\":"
                      << static_cast<unsigned int>(file_data.byFileType) << ","
                      << "\"locked\":"
                      << (file_data.byLocked ? "true" : "false") << ","
                      << "\"stream_type\":"
                      << static_cast<unsigned int>(file_data.byStreamType)
                      << "}\n";
            continue;
        }
        if (status == NET_DVR_FILE_NOFIND || status == NET_DVR_NOMOREFILE) {
            break;
        }
        std::cerr << "NET_DVR_FindNextFile_V40 failed with status " << status
                  << " (SDK error " << NET_DVR_GetLastError() << ")\n";
        exit_code = 12;
        break;
    }

    NET_DVR_FindClose_V30(find_handle);
    NET_DVR_Logout(user_id);
    NET_DVR_Cleanup();
    return exit_code;
}

}  // namespace

int main(int argc, char** argv) {
    if (argc == 2 && std::string_view(argv[1]) == "--check-sdk") {
        if (!NET_DVR_Init()) {
            std::cerr << "NET_DVR_Init failed: " << NET_DVR_GetLastError()
                      << '\n';
            return 3;
        }
        int decoder_port = -1;
        if (!PlayM4_GetPort(&decoder_port)) {
            std::cerr << "PlayM4_GetPort failed\n";
            NET_DVR_Cleanup();
            return 4;
        }
        const BOOL released_port = PlayM4_FreePort(decoder_port);
        const BOOL cleaned_up = NET_DVR_Cleanup();
        if (!released_port || !cleaned_up) {
            std::cerr << "SDK initialization cleanup failed\n";
            return 5;
        }
        std::cout << "HCNetSDK initialization and PlayCtrl port allocation ok "
                     "(capabilities: preview,playback,recordings)\n";
        return 0;
    }
    if (argc == 2 && std::string_view(argv[1]) == "--list-recordings") {
        std::signal(SIGTERM, handle_signal);
        std::signal(SIGINT, handle_signal);
        return list_recordings();
    }
    if (argc > 1 && std::string_view(argv[1]) != "--playback") {
        std::cerr << "Unknown helper option: " << argv[1] << '\n';
        return 2;
    }
    const bool playback_mode =
        (argc == 2 && std::string_view(argv[1]) == "--playback") ||
        env_or("HIKVISION_PLAYBACK") == "1" ||
        !env_or("HIKVISION_PLAYBACK_FILE").empty();
    const char* frame_fd_value = std::getenv("HIKVISION_FRAME_FD");
    const bool helper_mode = frame_fd_value != nullptr;
    std::signal(SIGTERM, handle_signal);
    std::signal(SIGINT, handle_signal);
    std::signal(SIGPIPE, SIG_IGN);

    const std::string host = env_or("HIKVISION_HOST", "192.168.101.8");
    const std::string username = env_or("HIKVISION_USERNAME");
    const std::string password = env_or("HIKVISION_PASSWORD");
    long port = 8000;
    long channel = 1;
    long run_seconds = helper_mode ? 0 : 15;
    long player_key_length = 128;
    long target_fps = 10;
    long stream_type = 0;
    long play_window = 0;
    long frame_fd = -1;
    if (username.empty() || password.empty()) {
        std::cerr << "Set HIKVISION_USERNAME and HIKVISION_PASSWORD\n";
        return 2;
    }
    if (!parse_integer("HIKVISION_PORT", 1, 65535, 8000, port) ||
        !parse_integer("HIKVISION_CHANNEL", 1, 256, 1, channel) ||
        !parse_integer("HIKVISION_RUN_SECONDS", helper_mode ? 0 : 1,
                       86400, helper_mode ? 0 : 15, run_seconds) ||
        !parse_integer("HIKVISION_PLAYM4_KEY_LENGTH", 16, 128, 128,
                       player_key_length) ||
        (player_key_length != 16 && player_key_length != 128) ||
        !parse_integer("HIKVISION_TARGET_FPS", 1, 30, 10, target_fps) ||
        !parse_integer("HIKVISION_STREAM_TYPE", 0, 1, 0, stream_type) ||
        !parse_integer("HIKVISION_PLAYM4_WINDOW", 0, 0xffffffffL, 0,
                       play_window) ||
        (helper_mode &&
         (!parse_integer("HIKVISION_FRAME_FD", 0, 0x7fffffffL, -1,
                         frame_fd) ||
          frame_fd < 0))) {
        std::cerr << "Invalid SDK parameter environment value\n";
        return 2;
    }

    TestState state;
    state.frame_output_fd = static_cast<int>(frame_fd);
    state.target_fps = static_cast<int>(target_fps);
    state.stream_type = static_cast<int>(stream_type);
    state.playback_mode = playback_mode;
    state.play_window = static_cast<PLAYM4_HWND>(play_window);
    const std::string stream_verification_code =
        env_or("HIKVISION_STREAM_VERIFICATION_CODE");
    state.stream_verification_code_configured.store(
        !stream_verification_code.empty());
    if (stream_verification_code.empty() && !playback_mode) {
        state.decoder_error_code.store(13);
        emit_diagnostics(state, helper_mode);
        std::cerr << "Set HIKVISION_STREAM_VERIFICATION_CODE to the "
                     "Platform Access stream encryption code\n";
        return 2;
    }
    if (!stream_verification_code.empty() &&
        !copy_field(state.stream_verification_code,
                    stream_verification_code)) {
        state.decoder_error_code.store(14);
        emit_diagnostics(state, helper_mode);
        std::cerr << "HIKVISION_STREAM_VERIFICATION_CODE exceeds "
                     "NET_SDK_MAX_VERIFICATION_CODE_LEN bytes\n";
        return 2;
    }

    const std::string playback_file = env_or("HIKVISION_PLAYBACK_FILE");
    const std::string start_time_text = env_or("HIKVISION_START_TIME");
    const std::string end_time_text = env_or("HIKVISION_END_TIME");
    long playback_pos = 0;
    long playback_speed_steps = 0;
    NET_DVR_TIME playback_start_time{};
    NET_DVR_TIME playback_end_time{};
    const bool has_playback_time_range =
        !start_time_text.empty() && !end_time_text.empty() &&
        parse_dvr_time(start_time_text, playback_start_time) &&
        parse_dvr_time(end_time_text, playback_end_time);
    if (!parse_integer("HIKVISION_PLAYBACK_POS", 0, 99, 0, playback_pos) ||
        !parse_integer("HIKVISION_PLAYBACK_SPEED_STEPS", -4, 4, 0,
                       playback_speed_steps) ||
        (playback_mode && playback_file.empty() && !has_playback_time_range)) {
        std::cerr << "Set HIKVISION_PLAYBACK_FILE or valid "
                     "HIKVISION_START_TIME/HIKVISION_END_TIME for playback\n";
        return 2;
    }
    state.playback_speed_steps = static_cast<int>(playback_speed_steps);

    NET_DVR_SetLogToFile(0, nullptr, TRUE);
    if (!NET_DVR_Init()) {
        state.sdk_init_status.store(-1);
        state.sdk_error_code.store(NET_DVR_GetLastError());
        emit_diagnostics(state, helper_mode);
        std::cerr << "NET_DVR_Init failed: " << NET_DVR_GetLastError() << '\n';
        return 3;
    }
    state.sdk_init_status.store(1);
    emit_diagnostics(state, helper_mode);
    NET_DVR_SetConnectTime(5000, 3);
    NET_DVR_SetReconnect(10000, TRUE);

    NET_DVR_USER_LOGIN_INFO login_info{};
    NET_DVR_DEVICEINFO_V40 device_info{};
    if (!copy_field(login_info.sDeviceAddress, host) ||
        !copy_field(login_info.sUserName, username) ||
        !copy_field(login_info.sPassword, password)) {
        state.login_status.store(-1);
        emit_diagnostics(state, helper_mode);
        std::cerr << "Host or credential exceeds the SDK field size\n";
        NET_DVR_Cleanup();
        return 2;
    }
    login_info.wPort = static_cast<WORD>(port);
    login_info.bUseAsynLogin = FALSE;

    const LONG user_id = NET_DVR_Login_V40(&login_info, &device_info);
    if (user_id < 0) {
        state.login_status.store(-1);
        state.sdk_error_code.store(NET_DVR_GetLastError());
        emit_diagnostics(state, helper_mode);
        std::cerr << "NET_DVR_Login_V40 failed: " << NET_DVR_GetLastError()
                  << '\n';
        NET_DVR_Cleanup();
        return 4;
    }
    state.login_status.store(1);
    emit_diagnostics(state, helper_mode);
    std::cout << "login=ok\n";

    std::array<char, 16> key{};
    std::string key_source;
    if (!get_stream_key(user_id, key, key_source)) {
        state.aes_key_status.store(-1);
        state.sdk_error_code.store(NET_DVR_GetLastError());
        emit_diagnostics(state, helper_mode);
        if (!playback_mode) {
            NET_DVR_Logout(user_id);
            NET_DVR_Cleanup();
            return 5;
        }
    } else {
        state.aes_key_status.store(1);
        emit_diagnostics(state, helper_mode);
        if (!NET_DVR_SetSDKSecretKey(user_id, key.data())) {
            state.sdk_key_status.store(-1);
            state.sdk_error_code.store(NET_DVR_GetLastError());
            emit_diagnostics(state, helper_mode);
            std::cerr << "NET_DVR_SetSDKSecretKey failed: "
                      << NET_DVR_GetLastError() << '\n';
            if (!playback_mode) {
                NET_DVR_Logout(user_id);
                NET_DVR_Cleanup();
                return 6;
            }
        } else {
            state.sdk_key_status.store(1);
            emit_diagnostics(state, helper_mode);
            std::cout << "SDK decryption key configured from " << key_source
                      << '\n';
        }
    }

    state.player_key_length = static_cast<int>(player_key_length);
    state.target_fps = static_cast<int>(target_fps);
    LONG stream_handle = -1;
    bool opened_by_name = false;
    if (playback_mode) {
        const auto open_by_time = [&]() -> LONG {
            if (!has_playback_time_range) {
                return -1;
            }
            NET_DVR_VOD_PARA vod_para{};
            vod_para.dwSize = sizeof(vod_para);
            vod_para.struIDInfo.dwSize = sizeof(vod_para.struIDInfo);
            vod_para.struIDInfo.dwChannel = static_cast<DWORD>(channel);
            vod_para.struBeginTime = playback_start_time;
            vod_para.struEndTime = playback_end_time;
            vod_para.hWnd = 0;
            vod_para.byStreamType = static_cast<BYTE>(stream_type);
            vod_para.byOptimalStreamType = 1;
            return NET_DVR_PlayBackByTime_V40(user_id, &vod_para);
        };
        const auto open_by_name = [&]() -> LONG {
            if (playback_file.empty()) {
                return -1;
            }
            char file_name[100]{};
            if (!copy_field(file_name, playback_file)) {
                return -1;
            }
            const LONG handle = NET_DVR_PlayBackByName(user_id, file_name, 0);
            if (handle >= 0) {
                opened_by_name = true;
            }
            return handle;
        };

        if (playback_pos > 0 && has_playback_time_range) {
            stream_handle = open_by_time();
            if (stream_handle < 0) {
                stream_handle = open_by_name();
            }
        } else {
            stream_handle = open_by_name();
            if (stream_handle < 0) {
                stream_handle = open_by_time();
            }
        }
        if (stream_handle < 0) {
            state.preview_status.store(-1);
            state.sdk_error_code.store(NET_DVR_GetLastError());
            emit_diagnostics(state, helper_mode);
            std::cerr << "NET_DVR_PlayBack failed: " << NET_DVR_GetLastError()
                      << '\n';
            NET_DVR_Logout(user_id);
            NET_DVR_Cleanup();
            return 7;
        }
        if (!NET_DVR_SetPlayDataCallBack_V40(stream_handle, stream_callback,
                                             &state)) {
            state.preview_status.store(-1);
            state.sdk_error_code.store(NET_DVR_GetLastError());
            emit_diagnostics(state, helper_mode);
            std::cerr << "NET_DVR_SetPlayDataCallBack_V40 failed: "
                      << NET_DVR_GetLastError() << '\n';
            NET_DVR_StopPlayBack(stream_handle);
            NET_DVR_Logout(user_id);
            NET_DVR_Cleanup();
            return 7;
        }
        DWORD start_offset = 0;
        if (!NET_DVR_PlayBackControl_V40(stream_handle, NET_DVR_PLAYSTART,
                                         nullptr, 0, nullptr, nullptr) &&
            !NET_DVR_PlayBackControl_V40(stream_handle, NET_DVR_PLAYSTART,
                                         &start_offset, sizeof(start_offset),
                                         nullptr, nullptr)) {
            state.preview_status.store(-1);
            state.sdk_error_code.store(NET_DVR_GetLastError());
            emit_diagnostics(state, helper_mode);
            std::cerr << "NET_DVR_PLAYSTART failed: " << NET_DVR_GetLastError()
                      << '\n';
            NET_DVR_StopPlayBack(stream_handle);
            NET_DVR_Logout(user_id);
            NET_DVR_Cleanup();
            return 7;
        }
        if (opened_by_name && playback_pos > 0) {
            DWORD seek_pos = static_cast<DWORD>(playback_pos);
            NET_DVR_PlayBackControl_V40(stream_handle, NET_DVR_PLAYSETPOS,
                                        &seek_pos, sizeof(seek_pos), nullptr,
                                        nullptr);
        }
        for (long step = 0; step < playback_speed_steps; ++step) {
            NET_DVR_PlayBackControl_V40(stream_handle, NET_DVR_PLAYFAST,
                                        nullptr, 0, nullptr, nullptr);
        }
        for (long step = 0; step > playback_speed_steps; --step) {
            NET_DVR_PlayBackControl_V40(stream_handle, NET_DVR_PLAYSLOW,
                                        nullptr, 0, nullptr, nullptr);
        }
        state.playback_progress.store(static_cast<int>(playback_pos));
    } else {
        NET_DVR_PREVIEWINFO preview_info{};
        preview_info.hPlayWnd = 0;
        preview_info.lChannel = static_cast<LONG>(channel);
        preview_info.dwStreamType = static_cast<DWORD>(stream_type);
        preview_info.dwLinkMode = 0;
        preview_info.bBlocked = FALSE;
        preview_info.byProtoType = 0;

        stream_handle = NET_DVR_RealPlay_V40(user_id, &preview_info,
                                             stream_callback, &state);
        if (stream_handle < 0) {
            state.preview_status.store(-1);
            state.sdk_error_code.store(NET_DVR_GetLastError());
            emit_diagnostics(state, helper_mode);
            std::cerr << "NET_DVR_RealPlay_V40 failed: "
                      << NET_DVR_GetLastError() << '\n';
            NET_DVR_Logout(user_id);
            NET_DVR_Cleanup();
            return 7;
        }
    }

    state.preview_status.store(1);
    emit_diagnostics(state, helper_mode);
    std::cout << (playback_mode ? "playback=started channel="
                                : "preview=started channel=")
              << channel
              << " stream=" << (stream_type == 0 ? "main" : "sub")
              << " duration_seconds=" << run_seconds << '\n';
    const auto start_time = std::chrono::steady_clock::now();
    auto last_diagnostics_time = start_time;
    if (helper_mode) {
        while (g_keep_running) {
            const auto now = std::chrono::steady_clock::now();
            if (state.player_error.load() != 0 ||
                state.decoder_error_code.load() != 0) {
                break;
            }
            if (state.decoded_frames.load() == 0 &&
                now - start_time >= std::chrono::seconds(15)) {
                if (playback_mode &&
                    !state.stream_verification_code_configured.load() &&
                    state.video_encrypt_type.load() > 0) {
                    state.decoder_error_code.store(13);
                } else {
                    state.decoder_error_code.store(9);
                }
                emit_diagnostics(state, true);
                break;
            }
            if (run_seconds > 0 &&
                now - start_time >= std::chrono::seconds(run_seconds)) {
                break;
            }
            if (now - last_diagnostics_time >= std::chrono::seconds(1)) {
                if (playback_mode) {
                    NET_DVR_TIME osd_time{};
                    if (NET_DVR_GetPlayBackOsdTime(stream_handle, &osd_time) &&
                        osd_time.dwYear >= 2000 && osd_time.dwMonth >= 1 &&
                        osd_time.dwMonth <= 12 && osd_time.dwDay >= 1 &&
                        osd_time.dwDay <= 31) {
                        std::lock_guard<std::mutex> osd_lock(
                            state.osd_time_mutex);
                        state.playback_osd_time = format_dvr_time(osd_time);
                    }
                    DWORD progress = 0;
                    DWORD out_len = 0;
                    if (NET_DVR_PlayBackControl_V40(
                            stream_handle, NET_DVR_PLAYGETPOS, nullptr, 0,
                            &progress, &out_len)) {
                        state.playback_progress.store(
                            static_cast<int>(progress));
                        if (progress == 100) {
                            std::this_thread::sleep_for(
                                std::chrono::milliseconds(400));
                            emit_diagnostics(state, true);
                            break;
                        }
                        if (progress > 100) {
                            state.sdk_error_code.store(NET_DVR_GetLastError());
                            emit_diagnostics(state, true);
                            break;
                        }
                    }
                }
                emit_diagnostics(state, true);
                last_diagnostics_time = now;
            }
            std::this_thread::sleep_for(std::chrono::milliseconds(100));
        }
    } else {
        std::this_thread::sleep_for(std::chrono::seconds(run_seconds));
    }

    const BOOL stopped = playback_mode ? NET_DVR_StopPlayBack(stream_handle)
                                       : NET_DVR_StopRealPlay(stream_handle);
    const int player_port = state.player_port.exchange(-1);
    unsigned int last_player_error = 0;
    if (player_port >= 0) {
        last_player_error = PlayM4_GetLastError(player_port);
        PlayM4_Stop(player_port);
        PlayM4_CloseStream(player_port);
        PlayM4_FreePort(player_port);
    }
    const BOOL logged_out = NET_DVR_Logout(user_id);
    const BOOL cleaned_up = NET_DVR_Cleanup();
    emit_diagnostics(state, helper_mode);

    if (!stopped || !logged_out || !cleaned_up) {
        std::cerr << "SDK cleanup reported an error\n";
    }

    const std::uint64_t frames = state.decoded_frames.load();
    std::cout << "decoded_frames=" << frames
              << " dimensions=" << state.width.load() << 'x'
              << state.height.load()
              << " system_headers=" << state.system_headers.load()
              << " stream_chunks=" << state.stream_chunks.load()
              << " stream_bytes=" << state.stream_bytes.load()
              << " input_failures=" << state.input_failures.load() << '\n';
    std::cout << "PlayCtrl last_error=" << last_player_error << '\n';
    if (state.encrypt_info_seen.load()) {
        std::cout << "PlayCtrl encryption metadata: video="
                  << state.video_encrypt_type.load()
                  << " audio=" << state.audio_encrypt_type.load()
                  << " decoder_key_set=" << state.decoder_key_set.load()
                  << '\n';
    }
    if (state.player_error.load() != 0) {
        std::cerr << "PlayCtrl setup/input stage "
                  << state.player_error.load() << " failed; error "
                  << state.player_error_code.load() << '\n';
        return 8;
    }
    if (state.decoder_error_code.load() == 10 ||
        state.decoder_error_code.load() == 11) {
        return 11;
    }
    if (frames == 0) {
        std::cerr << "No decoded frames received\n";
        return 9;
    }
    return stopped && logged_out && cleaned_up ? 0 : 10;
}
