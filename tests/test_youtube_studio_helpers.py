import sys
import types
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = PROJECT_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))


FAKE_SELENIUM_MODULES = (
    "selenium",
    "selenium.webdriver",
    "selenium.webdriver.common",
    "selenium.webdriver.common.action_chains",
    "selenium.webdriver.common.by",
    "selenium.webdriver.common.keys",
    "selenium.webdriver.support",
    "selenium.webdriver.support.expected_conditions",
    "selenium.webdriver.support.ui",
)


def install_fake_selenium() -> dict[str, types.ModuleType | None]:
    original_modules = {name: sys.modules.get(name) for name in FAKE_SELENIUM_MODULES}
    selenium = types.ModuleType("selenium")
    webdriver = types.ModuleType("selenium.webdriver")
    common = types.ModuleType("selenium.webdriver.common")
    action_chains = types.ModuleType("selenium.webdriver.common.action_chains")
    by = types.ModuleType("selenium.webdriver.common.by")
    keys = types.ModuleType("selenium.webdriver.common.keys")
    support = types.ModuleType("selenium.webdriver.support")
    expected_conditions = types.ModuleType(
        "selenium.webdriver.support.expected_conditions"
    )
    ui = types.ModuleType("selenium.webdriver.support.ui")

    class FakeActionChains:
        def __init__(self, _driver):
            pass

        def move_to_element(self, _element):
            return self

        def perform(self):
            return None

    class FakeBy:
        CSS_SELECTOR = "css selector"
        ID = "id"
        NAME = "name"
        TAG_NAME = "tag name"
        XPATH = "xpath"

    class FakeKeys:
        BACKSPACE = "BACKSPACE"
        CONTROL = "CONTROL"
        ESCAPE = "ESCAPE"

    class FakeWebDriverWait:
        def __init__(self, *_args, **_kwargs):
            pass

        def until(self, condition):
            return condition

    action_chains.ActionChains = FakeActionChains
    by.By = FakeBy
    keys.Keys = FakeKeys
    expected_conditions.element_to_be_clickable = lambda locator: locator
    expected_conditions.presence_of_element_located = lambda locator: locator
    ui.WebDriverWait = FakeWebDriverWait

    for module in (
        selenium,
        webdriver,
        common,
        action_chains,
        by,
        keys,
        support,
        expected_conditions,
        ui,
    ):
        sys.modules[module.__name__] = module

    return original_modules


def restore_modules(original_modules: dict[str, types.ModuleType | None]) -> None:
    for name, original in original_modules.items():
        if original is None:
            sys.modules.pop(name, None)
        else:
            sys.modules[name] = original


_original_selenium_modules = install_fake_selenium()

from youtube_studio import clean_description  # noqa: E402
from youtube_studio import clean_title  # noqa: E402
from youtube_studio import visibility_config  # noqa: E402

restore_modules(_original_selenium_modules)


class YouTubeStudioHelperTests(unittest.TestCase):
    def test_clean_title_collapses_whitespace_and_caps_length(self):
        title = "  Samsung   launches\nnew   foldable  " + "x" * 120

        cleaned = clean_title(title)

        self.assertNotIn("\n", cleaned)
        self.assertNotIn("  ", cleaned)
        self.assertLessEqual(len(cleaned), 95)

    def test_clean_description_caps_length(self):
        self.assertEqual(len(clean_description("a" * 5000)), 4500)

    def test_visibility_config_rejects_unknown_visibility(self):
        self.assertEqual(visibility_config("public")["radio"], "PUBLIC")
        self.assertEqual(visibility_config("unlisted")["radio"], "UNLISTED")

        with self.assertRaises(ValueError):
            visibility_config("private")


if __name__ == "__main__":
    unittest.main()
