from config import ROOT_DIR

try:
    from termcolor import colored
except ModuleNotFoundError:
    def colored(text, *_args, **_kwargs):
        return text

def print_banner() -> None:
    """
    Prints the introductory ASCII Art Banner.

    Returns:
        None
    """
    with open(f"{ROOT_DIR}/assets/banner.txt", "r") as file:
        print(colored(file.read(), "green"))
