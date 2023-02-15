import os
from datetime import datetime
from enum import Enum
from typing import TextIO, Optional

from colorama import Fore, Style


class LogLevel(Enum):
    LOG_ERROR = 0
    LOG_WARNING = 1
    LOG_INFO = 2
    LOG_SUCCESS = 3
    LOG_DEBUG = 4


class Logger:
    def __init__(self):
        self.log_file_dir: str = ""
        self.debug: bool = False
        self.last_log_newline: bool = True

        self.log_file_path: str = ""
        self.log_file: Optional[TextIO] = None

    def init(self, log_file_dir: str, debug: bool = False):
        self.log_file_dir: str = log_file_dir
        self.debug: bool = debug
        self.last_log_newline: bool = True

        # create the log directory if it does not exists
        if not os.path.exists(self.log_file_dir):
            os.mkdir(self.log_file_dir)

        # set the log file name with the current datetime
        self.log_file_path: str = self.log_file_dir + '/' + datetime.now().strftime("%Y%m%d_%H%M%S") + '.html'

        # open the logfile for writing
        self.log_file: TextIO = open(self.log_file_path, "wt")

        if self.debug:
            print(f"{Fore.CYAN}Debug ENABLED{Style.RESET_ALL}")

    def log(self, message: str, end: str = "\r\n", no_date: bool = False, log_type: LogLevel = LogLevel.LOG_INFO,
            no_prefix: bool = False, force_newline: bool = False):

        if log_type == LogLevel.LOG_DEBUG and not self.debug:
            return

        str_print = ""
        str_file = ""
        str_date = datetime.now().strftime("%Y/%m/%d %H:%M:%S")

        if not self.last_log_newline and force_newline:
            str_print = "\r\n"
            str_file = "<br/>\r\n"

        if not no_date:
            str_print = str_print + str_date + " - "
            str_file = str_print + str_date + " - "

        if log_type == LogLevel.LOG_ERROR:
            str_print = str_print + f"{Fore.RED}"
            if not no_prefix:
                str_print = str_print + "ERROR: "
            str_file = str_file + "<font color='red'>"
            if not no_prefix:
                str_file = str_file + "ERROR: "
        elif log_type == LogLevel.LOG_WARNING:
            str_print = str_print + f"{Fore.YELLOW}"
            if not no_prefix:
                str_print = str_print + "WARNING: "
            str_file = str_file + "<font color='yellow'>"
            if not no_prefix:
                str_file = str_file + "WARNING: "
        elif log_type == LogLevel.LOG_SUCCESS:
            str_print = str_print + f"{Fore.GREEN}"
            str_file = str_file + "<font color='green'>"
        elif log_type == LogLevel.LOG_DEBUG:
            str_print = str_print + f"{Fore.CYAN}"
            str_file = str_file + "<font color='cyan'>"

        str_print = str_print + message
        str_file = str_file + message

        if log_type == LogLevel.LOG_ERROR or log_type == LogLevel.LOG_WARNING or log_type == LogLevel.LOG_SUCCESS or log_type == LogLevel.LOG_DEBUG:
            str_print = str_print + f"{Style.RESET_ALL}"
            str_file = str_file + "</font>"

        if end == "":
            self.last_log_newline = False
            print(str_print, end="")
        else:
            self.last_log_newline = True
            print(str_print)
        if not self.log_file.closed:
            if end == "":
                self.log_file.write(str_file)
                self.log_file.flush()
            else:
                self.log_file.write(str_file + '</br>' + end)
                self.log_file.flush()

    def close(self):
        self.log_file.flush()
        self.log_file.close()
