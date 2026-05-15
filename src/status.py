import sys

try:
    from termcolor import colored
except ModuleNotFoundError:
    def colored(text, *_args, **_kwargs):
        return text


def _ensure_utf8_stdout() -> None:
    """Prefer UTF-8 output when the host stream allows reconfiguration."""
    stream = getattr(sys, "stdout", None)
    reconfigure = getattr(stream, "reconfigure", None)
    if reconfigure is None:
        return
    try:
        reconfigure(encoding="utf-8", errors="replace")
    except (OSError, ValueError):
        pass


def _safe_print(message: str) -> None:
    try:
        print(message)
    except UnicodeEncodeError:
        print(str(message).encode("ascii", "replace").decode("ascii"))


def _safe_input(prompt: str) -> str:
    try:
        return input(prompt)
    except UnicodeEncodeError:
        fallback = str(prompt).encode("ascii", "replace").decode("ascii")
        return input(fallback)


_ensure_utf8_stdout()

def error(message: str, show_emoji: bool = True) -> None:
    """
    Prints an error message.

    Args:
        message (str): The error message
        show_emoji (bool): Whether to show the emoji

    Returns:
        None
    """
    emoji = "❌" if show_emoji else ""
    _safe_print(colored(f"{emoji} {message}", "red"))

def success(message: str, show_emoji: bool = True) -> None:
    """
    Prints a success message.

    Args:
        message (str): The success message
        show_emoji (bool): Whether to show the emoji

    Returns:
        None
    """
    emoji = "✅" if show_emoji else ""
    _safe_print(colored(f"{emoji} {message}", "green"))

def info(message: str, show_emoji: bool = True) -> None:
    """
    Prints an info message.

    Args:
        message (str): The info message
        show_emoji (bool): Whether to show the emoji

    Returns:
        None
    """
    emoji = "ℹ️" if show_emoji else ""
    _safe_print(colored(f"{emoji} {message}", "magenta"))

def warning(message: str, show_emoji: bool = True) -> None:
    """
    Prints a warning message.

    Args:
        message (str): The warning message
        show_emoji (bool): Whether to show the emoji

    Returns:
        None
    """
    emoji = "⚠️" if show_emoji else ""
    _safe_print(colored(f"{emoji} {message}", "yellow"))

def question(message: str, show_emoji: bool = True) -> str:
    """
    Prints a question message and returns the user's input.

    Args:
        message (str): The question message
        show_emoji (bool): Whether to show the emoji

    Returns:
        user_input (str): The user's input
    """
    emoji = "❓" if show_emoji else ""
    return _safe_input(colored(f"{emoji} {message}", "magenta"))
