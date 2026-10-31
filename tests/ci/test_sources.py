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


def test_github_com_is_vetted_only_for_the_tracked_competitors_orgs():
    """D34/D49: github.com is a place, not one company. The HN item github.com/cognitionai/devin-vuln-fixes was
    auto-published at strict while github.com was vetted as a whole host."""
    assert sources.vetted_group("https://github.com/github/codeql-action/releases/tag/v4") == "first_party"
    assert sources.is_vetted("https://github.com/Cloudsmith-io/cloudsmith-cli/releases")
    assert not sources.is_vetted("https://github.com/cognitionai/devin-vuln-fixes")
    assert not sources.is_vetted("https://github.com/")  # the host alone is no org
    assert sources.is_vetted("https://github.blog/changelog/x")  # other GitHub hosts are unchanged


def test_every_tracked_repo_owner_is_a_vetted_org():
    from ci.config import load

    owners = {r.split("/")[0].lower() for c in load().competitors for r in c.github_repos}
    assert owners and owners <= sources.github_orgs()
