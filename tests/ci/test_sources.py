"""Vetted sources (D9, D34): the approved list and the host matching."""
from ci import sources


def test_approved_list_has_10_first_party_and_20_trade_press_hosts():
    lists = sources.load()
    assert (len(lists["first_party"]), len(lists["trade_press"])) == (10, 20)


def test_subdomains_match_and_lookalikes_do_not():
    assert sources.vetted_group("https://updates.snyk.io/x") == "first_party"
    assert sources.vetted_group("https://www.theregister.com/2026/10/30/a") == "trade_press"
    assert not sources.is_vetted("https://notsnyk.io/x")  # a suffix that is not a subdomain
    assert not sources.is_vetted("https://snyk.io.evil.example/x")
    assert not sources.is_vetted("https://www.businesswire.com/news/1")  # press wires were left off


def test_custom_list(tmp_path):
    p = tmp_path / "v.yaml"
    p.write_text("first_party: [Example.com]\ntrade_press: []\n")
    assert sources.is_vetted("https://blog.example.com/a", p) and not sources.is_vetted("https://x.org", p)
