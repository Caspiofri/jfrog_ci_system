"""config/tracked_pages.yaml and its loader: the pages change detection reads and the D13 axes each informs."""
import pytest
from pydantic import ValidationError

from ci import config as ci_config
from ci.changes import config


def test_tracked_pages_config_is_valid_and_covers_jfrog_and_every_competitor():
    pages = config.load()
    competitors = {c.key for c in ci_config.load().competitors} - {"industry"}
    assert set(pages.competitors) == competitors | {config.JFROG}
    for key, tracked in pages.competitors.items():
        assert tracked, key
        assert all(p.url.startswith("https://") for p in tracked)


def test_an_axis_informed_by_two_pages_of_one_competitor_is_rejected():
    with pytest.raises(ValidationError, match="informed by both"):
        config.TrackedPages.model_validate({"competitors": {"x": [
            {"key": "a", "url": "https://x.test/a", "page_type": "pricing", "axes": ["pricing_model"]},
            {"key": "b", "url": "https://x.test/b", "page_type": "product", "axes": ["pricing_model"]}]}})


@pytest.mark.parametrize("page", [
    {"key": "a", "url": "https://x.test", "page_type": "pricing", "axes": ["price"]},  # not a D13 axis
    {"key": "a", "url": "https://x.test", "page_type": "blog", "axes": ["pricing_model"]},
    {"key": "A/b", "url": "https://x.test", "page_type": "pricing", "axes": ["pricing_model"]},
    {"key": "a", "url": "https://x.test", "page_type": "pricing", "axes": []},
])
def test_invalid_pages_are_rejected(page):
    with pytest.raises(ValidationError):
        config.TrackedPage.model_validate(page)


def test_js_priced_pages_are_marked_and_get_the_default_note():
    pages = {(c, p.key): p for c, p in config.load().pages()}
    for key in [("gitlab", "pricing"), ("snyk", "plans"), ("aws_codeartifact", "pricing")]:
        assert pages[key].prices_on_page is False
        assert pages[key].note == config.PRICES_OFF_PAGE_NOTE
    assert pages[("jfrog", "pricing")].prices_on_page and pages[("jfrog", "pricing")].note == ""
    custom = config.TrackedPage(key="a", url="https://x.test", page_type="pricing", axes=["pricing_model"],
                                prices_on_page=False, note="tables load later")
    assert custom.note == "tables load later"

