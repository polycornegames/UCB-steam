import os
from typing import Final

from libraries import LOGGER
from libraries.AWS import AWS_S3
from libraries.logger import LogLevel
from libraries.store import Store

# region ERRORS NUMBER
# must be over 10000
AWS_S3_TEMP_FILE_CREATION_TEST_FAILED: Final[int] = 11001
AWS_S3_UPLOAD_TEST_FAILED: Final[int] = 11002
AWS_S3_DELETE_TEST_FAILED: Final[int] = 11003
AWS_S3_CLEAN_TEST_FAILED: Final[int] = 11004
AWS_S3_UPLOAD_FAILED: Final[int] = 11005
AWS_S3_DOWNLOADED_FILE_DOESNT_EXISTS: Final[int] = 11006
# endregion


class S3(Store):
    def __init__(self, base_path: str, home_path: str, build_path: str, download_path: str, check_project_version: bool, parameters: dict,
                 built: bool = False):
        super().__init__(base_path, home_path, build_path, download_path, check_project_version, parameters, built)
        self.name = "s3"

        if 's3' not in self.parameters.keys():
            LOGGER.log("Configuration file have no 's3' section", log_type=LogLevel.LOG_ERROR)
            return

        if 'export_path' not in self.parameters['s3'].keys():
            LOGGER.log("'s3' configuration file section have no 'export_path' value", log_type=LogLevel.LOG_ERROR)
            return

        self.export_path: str = self.parameters['s3']['export_path']

        if 'enabled' in self.parameters[self.name].keys():
            self.enabled = self.parameters[self.name]['enabled']

    def install(self, simulate: bool = False) -> int:
        ok: int = 0

        return ok

    def test(self) -> int:
        exitcode: int = 0

        LOGGER.log("Testing AWS S3 connection...", end="")
        os.system('echo "Success" > ' + self.base_path + '/test_successful.txt')
        ok = AWS_S3.s3_upload_file(self.base_path + '/test_successful.txt',
                                   f"{self.export_path}/test_successful.txt")
        if ok != 0:
            LOGGER.log(f"Error uploading file to S3 {self.export_path}. Check the IAM permissions",
                       log_type=LogLevel.LOG_ERROR,
                       no_date=True)
            exitcode = AWS_S3_UPLOAD_TEST_FAILED
        ok = AWS_S3.s3_delete_file(f"{self.export_path}/test_successful.txt")
        if ok != 0:
            LOGGER.log(f"Error deleting file from S3 {self.export_path}. Check the IAM permissions",
                       log_type=LogLevel.LOG_ERROR,
                       no_date=True)
            exitcode = AWS_S3_DELETE_TEST_FAILED
        os.remove(self.base_path + '/test_successful.txt')
        ok = os.path.exists(self.base_path + '/test_successful.txt')
        if ok != 0:
            LOGGER.log("Error deleting after connecting to S3", log_type=LogLevel.LOG_ERROR, no_date=True)
            exitcode = AWS_S3_CLEAN_TEST_FAILED
        LOGGER.log("OK", log_type=LogLevel.LOG_SUCCESS, no_date=True)

        return exitcode

    def build(self, app_version: str = "", no_live: bool = False, simulate: bool = False, force: bool = False) -> int:
        for build_target in self.build_targets.values():
            build_app_version: str = app_version
            if app_version == "":
                build_app_version = build_target.version

            # check if the build target have a valid downloaded_file
            if not simulate and not os.path.exists(build_target.downloaded_file_path):
                return AWS_S3_DOWNLOADED_FILE_DOESNT_EXISTS

            if self.check_project_version:
                s3path = f"{self.export_path}/{build_target.name}-{build_app_version}.zip"
            else:
                s3path = f"{self.export_path}/{build_target.name}.zip"

            LOGGER.log(f" Uploading copy to S3 {s3path} ...", end="")
            if not simulate:
                ok = AWS_S3.s3_upload_file(build_target.downloaded_file_path, s3path)
            else:
                ok = 0

            if ok != 0:
                LOGGER.log(f"  Error uploading file \"{build_target.name}.zip\" to AWS {s3path}. Check the IAM permissions", log_type=LogLevel.LOG_ERROR, no_date=True)
                return AWS_S3_UPLOAD_FAILED

            LOGGER.log("OK", log_type=LogLevel.LOG_SUCCESS, no_date=True)

        return 0
