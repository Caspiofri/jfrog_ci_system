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


def test_inside_a_vetted_org_only_the_orgs_own_pages_are_vetted():
    """D53 (3): releases, tags, blob/tree and changelog pages are the org's; issues, discussions, PRs and
    advisories can be written by anyone, so they are held for review (D56: advisories stay unvetted for now)."""
    gh = "https://github.com/github/codeql-action"
    for vetted in ("/releases/tag/v4", "/releases", "/tags", "/blob/main/README.md", "/tree/main/src",
                   "/blob/main/CHANGELOG.md", "/wiki/Changelog"):
        assert sources.is_vetted(gh + vetted), vetted
    for unvetted in ("", "/issues/12", "/discussions/3", "/pull/9", "/pulls", "/security/advisories/GHSA-x",
                     "/wiki/Home", "/actions"):
        assert not sources.is_vetted(gh + unvetted), unvetted
    assert not sources.is_vetted("https://github.com/github")  # the org page is not a release
    assert not sources.is_vetted("https://github.com/cognitionai/devin-vuln-fixes/releases/tag/v1")  # not a vetted org


def test_gist_is_never_vetted():
    assert not sources.is_vetted("https://gist.github.com/github/0123abcd")
    assert not sources.is_vetted("https://gist.github.com/anyone/0123abcd")


def test_gitlab_com_is_vetted_only_for_gitlab_org_and_gitlab_com():
    assert sources.gitlab_orgs() == {"gitlab-org", "gitlab-com"}
    assert sources.is_vetted("https://gitlab.com/gitlab-org/gitlab/-/releases/v19.5.1-ee")
    assert sources.is_vetted("https://gitlab.com/gitlab-org/security/gitlab/-/tags/v19.5.1")  # nested group
    assert sources.is_vetted("https://gitlab.com/gitlab-com/www-gitlab-com/-/blob/master/CHANGELOG.md")
    assert sources.is_vetted("https://gitlab.com/gitlab-org/gitlab/-/tree/master/doc")
    for unvetted in ("https://gitlab.com/gitlab-org/gitlab/-/issues/1", "https://gitlab.com/gitlab-org/gitlab/-/merge_requests/2",
                     "https://gitlab.com/gitlab-org/gitlab", "https://gitlab.com/someone/gitlab/-/releases/v1",
                     "https://gitlab.com/"):
        assert not sources.is_vetted(unvetted), unvetted
    assert sources.is_vetted("https://about.gitlab.com/releases/2026/10/22/x/")  # GitLab's own hosts are unchanged
    assert sources.is_vetted("https://docs.gitlab.com/releases/patches/patch-release-gitlab-19-5-1-released/")
