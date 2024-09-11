from beaker_util.main import main
import sys

def launch():
    argv = ["launch"] + sys.argv[1:]
    main(argv)
