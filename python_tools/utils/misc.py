from inspect import getmembers
from sys import exit
from types import ModuleType


def confirm_config(config_module: ModuleType):
    members = getmembers(config_module)
    params = sorted(
        i for i in members if not i[0].startswith("__") and not "." in str(i[1])
    )
    if params:
        print(
            "The following parameters have been defined in the "
            f"{config_module.__name__}.py file:"
        )
        for param in params:
            print(f"{param[0]}:\t{param[1]}")
        answer = input("\nAre you OK with these settings (y/*)?\t: ")
        if answer != "y":
            exit(1)
