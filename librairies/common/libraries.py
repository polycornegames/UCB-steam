# region HELPER LIBRARY
def print_help():
    print(
        f"Unity-steam.py [--platform=(standalonelinux64, standaloneosxuniversal, standalonewindows64)] [--environment=(environment1, environment2, ...)] [--store=(store1,store2,...)] [--nolive] [--force] [--version=<version>] [--install] [--nodownload] [--nos3upload] [--noupload] [--noclean] [--nonotify] [--noshutdown] [--noemail] [--simulate] [--showconfig | --showdiag] [--steamuser=<steamuser>] [--steampassword=<steampassword>]")


# endregion

# region FILE
def replace_in_file(file, haystack, needle):
    # read input file
    fin = open(file, "rt")
    # read file contents to string
    data = fin.read()
    # replace all occurrences of the required string
    data = data.replace(str(haystack), str(needle))
    # close the input file
    fin.close()
    # open the input file in write mode
    fin = open(file, "wt")
    # override the input file with the resulting data
    fin.write(data)
    # close the file
    fin.close()


def write_in_file(file, data):
    # open the input file in write mode
    fin = open(file, "wt")
    # override the input file with the resulting data
    fin.write(data)
    # close the file
    fin.close()


def read_from_file(file):
    # read input file
    fin = open(file, "rt")
    # read file contents to string
    data = fin.read()
    # close the input file
    fin.close()
    return data

# endregion
