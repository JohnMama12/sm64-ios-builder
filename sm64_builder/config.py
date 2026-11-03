from pathlib import Path


APP_NAME = "SM64 iOS Builder"
DEFAULT_REPOSITORY = "JohnMama12/sm64"

IOS_SDK_NAME = "iPhoneOS6.1.sdk"
IOS_SDK_VERSION = "6.1"
IOS_MIN_VERSION = "6.0"
IOS_ARCH = "armv7"
SDK_REPOSITORY = "qianjigui/iOS-sdks"
SDK_REPOSITORY_REF = "master"
SDK_DIRECTORY = "iPhoneOS6.1.sdk"

THEOS_REPOSITORY = "https://github.com/theos/theos.git"
TOOLCHAIN_RELEASE_API = (
    "https://api.github.com/repos/L1ghtmann/llvm-project/releases/latest"
)

PACKAGE_NAME = "com.sm64decomp.ios"
PACKAGE_ARCHITECTURE = "iphoneos-arm"
PACKAGE_MIN_IOS = "6.0"

KNOWN_ROMS = {
    "9bef1128717f958171a4afac3ed78ee2bb4e86ce": ("US", True),
    "8a20a5c83d6ceb0f0506cfc9fa20d8f438cafe51": ("JP", False),
    "4ac5721683d0e0b6bbb561b58a71740845dceea9": ("EU", False),
    "3f319ae697533a255a1003d09202379d78d5a2e0": ("Shindou", False),
}


def app_data_dir() -> Path:
    return Path.home() / ".local" / "share" / "sm64-ios-builder"


def theos_dir() -> Path:
    return app_data_dir() / "theos"
