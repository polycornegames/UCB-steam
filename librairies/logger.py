import os
from datetime import datetime
from enum import Enum
from typing import TextIO

from colorama import Fore, Style


class LogLevel(Enum):
    LOG_ERROR = 0
    LOG_WARNING = 1
    LOG_INFO = 2
    LOG_SUCCESS = 3


class Logger:
    def __init__(self, log_file_dir: str):
        self.log_file_dir: str = log_file_dir

        # create the log directory if it does not exists
        if not os.path.exists(self.log_file_dir):
            os.mkdir(self.log_file_dir)

        # set the log file name with the current datetime
        self.log_file_path: str = self.log_file_dir + '/' + datetime.now().strftime("%Y%m%d_%H%M%S") + '.html'

        # open the logfile for writing
        self.log_file: TextIO = open(self.log_file_path, "wt")

    def log(self, message: str, end: str = "\r\n", no_date: bool = False, log_type: LogLevel = LogLevel.LOG_INFO,
            no_prefix: bool = False):

        str_print = ""
        str_file = ""
        str_date = datetime.now().strftime("%Y/%m/%d %H:%M:%S")

        if not no_date:
            str_print = str_date + " - "
            str_file = str_date + " - "

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

        str_print = str_print + message
        str_file = str_file + message

        if log_type == LogLevel.LOG_ERROR or log_type == LogLevel.LOG_WARNING or log_type == LogLevel.LOG_SUCCESS:
            str_print = str_print + f"{Style.RESET_ALL}"
            str_file = str_file + "</font>"

        if end == "":
            print(str_print, end="")
        else:
            print(str_print)
        if not self.log_file.closed:
            if end == "":
                self.log_file.write(str_file)
                self.log_file.flush()
            else:
                self.log_file.write(str_file + '</br>' + end)
                self.log_file.flush()
