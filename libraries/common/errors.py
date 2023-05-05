from typing import Final

INVALID_PARAMETERS1: Final[int] = 10
INVALID_PARAMETERS2: Final[int] = 11

# region TESTS
APT_UPDATE_FAILED: Final[int] = 210
APT_INSTALL_FAILED: Final[int] = 211
PYTHON_INSTALLATION_FAILED: Final[int] = 212

PYTHON_INSTALL_DEPENDENCIES_FAILED: Final[int] = 240

AWS_DOWNLOAD_DEPENDENCIES_FAILED: Final[int] = 220
AWS_UNZIP_DEPENDENCIES_FAILED: Final[int] = 221
AWS_CLEAN_DEPENDENCIES_FAILED: Final[int] = 222
AWS_INSTALL_DEPENDENCIES_FAILED: Final[int] = 223

AWS_DDB_CONNECTION_TEST_FAILED: Final[int] = 230
AWS_DDB_CONNECTION_FAILED1: Final[int] = 231
AWS_DDB_CONNECTION_FAILED2: Final[int] = 232

UCB_STARTUP_SCRIPT_INSTALLATION_FAILED: Final[int] = 250
UCB_CHOWN_INSTALLATION_FAILED: Final[int] = 251
UCB_CONNECTION_TEST_FAILED: Final[int] = 252

EMAIL_CONNECTION_TEST_FAILED: Final[int] = 260
# endregion


UCB_NO_BUILD_AVAILABLE: Final[int] = 300
UCB_MISSING_BUILD_OBJECT: Final[int] = 301
UCB_MISSING_BUILD_FIELD_NUMBER: Final[int] = 302
UCB_BUILD_IS_FAILED: Final[int] = 303
UCB_MISSING_BUILD_FIELD_LASTBUILTREVISION: Final[int] = 304
UCB_BUILD_TOO_OLD: Final[int] = 305
UCB_CANNOT_UNZIP: Final[int] = 306
UCB_CANNOT_UPLOAD_TO_S3: Final[int] = 307
UCB_GET_BUILD_ERROR: Final[int] = 308
UCB_BUILD_IS_NOT_SUCCESSFUL: Final[int] = 309

NO_PACKAGE_COMPLETE: Final[int] = 400

VERSION_FILE_NOT_FOUND: Final[int] = 500

STORE_NO_UPLOAD_DONE: Final[int] = 600


def get_error_message(error_code: int) -> str:
    switcher = {
        UCB_MISSING_BUILD_OBJECT: "Missing build object",
        UCB_MISSING_BUILD_FIELD_NUMBER: "Missing builds field",
        UCB_BUILD_IS_FAILED: "The build seems to be a failed one",
        UCB_MISSING_BUILD_FIELD_LASTBUILTREVISION: "Missing builds field",
        UCB_BUILD_IS_NOT_SUCCESSFUL: "Build is not successful"
    }

    message: str = switcher.get(error_code, "Unknown error code")
    message = message + f" {str(error_code)}"

    return message