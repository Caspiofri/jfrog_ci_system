"""Classifier (D11) offline: rules settle clear items without the LLM, ambiguous ones go in id-keyed batches,
and a bad LLM answer degrades to low confidence instead of crashing."""

import pytest

from ci.classify import (
    CATEGORIES,
    LOW_CONFIDENCE,
    Classifier,
    aliases,
    mentions_jfrog,
    read_delimited_items,
    rule_category,
)
from ci.config import CIConfig, Competitor
from ci.llm import FakeLLM, LLMError

CFG = CIConfig(competitors=[
    Competitor(key="snyk", name="Snyk", feeds=[{"url": "https://updates.snyk.io/rss/"},
                                               {"url": "https://www.snyk.io/blog/feed/"}],
               github_repos=["snyk/cli"]),
    Competitor(key="gitlab", name="GitLab"),
    Competitor(key="aws", name="AWS", aliases=["CodeArtifact", "Amazon ECR", "Elastic Container Registry",
               "Amazon Inspector", "AWS Inspector"]),
    Competitor(key="industry", name="Industry"),
])


SNYK_FEED = "https://updates.snyk.io/rss/"


def _item(i, title, competitor="snyk", text="", source="google_news", origin="q"):
    if origin == "q" and source == "vendor_feed":
        origin = SNYK_FEED
    if origin == "q" and source == "github_releases":
        origin = "snyk/cli"
    return {"id": f"id{i}", "title": title, "competitor": competitor, "text": text, "source": source,
            "origin": origin, "text_status": "full"}


def _ids(schema):
    return schema["properties"]["items"]["items"]["properties"]["id"]["enum"]


def _answer_all(**fields):
    """A responder that answers every id in the batch with the given fields."""
    def respond(prompt, schema):
        return {"items": [{"id": i, "competitor": "industry", "category": "Security", "noise": False,
                           "confidence": 0.9, **fields} for i in _ids(schema)]}
    return respond


def test_categories_match_the_labeling_page():
    from ci.labeling.app import CATEGORIES as LABEL_CATEGORIES
    assert CATEGORIES == LABEL_CATEGORIES


def test_aliases_are_derived_from_name_and_key():
    assert set(aliases(CFG.by_key()["aws"])) == {"codeartifact", "amazon ecr", "elastic container registry",
                                                 "amazon inspector", "aws inspector"}  # never a bare "aws"
    assert set(aliases(CFG.by_key()["snyk"])) == {"snyk"}


@pytest.mark.parametrize("text,expected", [
    ("Compared with JFrog Artifactory", True), ("JFrog Xray found it", True), ("an x-ray of the market", False),
    ("nothing here", False), ("frogs jump", False),
    ("We migrated off Artifactory last year", True),  # Artifactory alone counts
    ("ARTIFACTORY and Nexus compared", True),
    ("Scanned with Xray inside Artifactory", True),  # Xray next to Artifactory
    ("Xray and V2Ray proxy configuration guide", False),  # bare Xray is a different tool
    ("An X-ray of the supply chain market", False),
    ("artifactory-like caching", True), ("jfrogging", False)])
def test_mentions_jfrog_regex(text, expected):
    assert mentions_jfrog({"title": "", "text": text}) is expected


@pytest.mark.parametrize("title,expected", [
    ("Snyk raises $100M Series F", "Funding/M&A/Partnerships"),
    ("Snyk patches critical vulnerability", "Security"),
    ("Snyk launches new MCP server", None),  # exactly one category must match
    ("Snyk adds MCP server", None),
    ("GitLab's new rate limit has a fatal flaw", None),  # no bare "flaw"
    ("Security extension for the GitHub Copilot app", None),  # Copilot in a security story is not AI & Agents
    ("Shadow AI Across Government: It's Three Problems, Not One", None),  # no bare "AI"
    ("Snyk CLI v1.2.3 released", "Product & Features"),
    ("Snyk appoints new CEO", "Leadership & Org"),
    ("A quiet Tuesday", None),
    ("AI agent exploits malicious packages", None),  # several topics: ambiguous
])
def test_rule_category(title, expected):
    assert rule_category(title)[0] == expected


def test_clear_items_are_settled_by_rules_without_an_llm_call():
    llm = FakeLLM()
    items = [_item(1, "Snyk patches critical vulnerability"),
             _item(2, "cli v1.1308.3", source="github_releases"),  # first-party repo, no name in the title
             _item(3, "Snyk pricing per seat changes"),
             _item(4, "We now support JFrog Artifactory", source="vendor_feed")]
    out = Classifier(llm, CFG).classify(items)
    assert llm.calls == []
    assert [c.method for c in out] == ["rules"] * 4
    assert [c.category for c in out] == ["Security", "Product & Features", "Pricing & Packaging",
                                         "Product & Features"]
    assert all(c.competitor == "snyk" and not c.noise for c in out)
    assert [c.mentions_jfrog for c in out] == [False, False, False, True]


@pytest.mark.parametrize("item,why", [
    (_item(1, "AI coding tool flaws found"), "not in the title"),  # Snyk named nowhere
    (_item(1, "New pricing plans announced", text="Snyk said... Snyk will"), "not in the title"),  # text only
    (_item(1, "Pricing update", text="Snyk once. GitLab GitLab GitLab"), "dominates"),
    (_item(1, "GitLab and Snyk ship a release", text="GitLab GitLab"), "dominates"),
    (_item(1, "Snyk stock hits 52-week high"), "chatter"),
    (_item(1, "Snyk at the summit"), "marketing"),
    (_item(1, "Snyk on a quiet Tuesday"), "no category keywords"),
    (_item(1, "Supply chain attack", competitor="industry"), "industry"),
])
def test_ambiguous_items_are_not_settled_by_rules(item, why):
    result, reason = Classifier(FakeLLM(), CFG).apply_rules(item)
    assert result is None and why in reason


def test_ambiguous_items_go_to_the_llm_once_per_batch():
    llm = FakeLLM(_answer_all())
    items = [_item(i, f"Story {i} about nothing") for i in range(23)] + [_item(99, "Snyk patches a CVE")]
    out = Classifier(llm, CFG, batch_size=10).classify(items)
    assert len(llm.calls) == 3  # 23 ambiguous items in batches of 10
    assert [len(_ids(s)) for _, s in llm.calls] == [10, 10, 3]
    assert [c.id for c in out] == [it["id"] for it in items]  # input order kept
    assert {c.method for c in out[:23]} == {"llm"} and out[23].method == "rules"
    assert out[0].competitor == "industry" and out[0].confidence == 0.9
    prompt = llm.calls[0][0]
    assert "id0" in prompt and "id10" not in prompt
    for category in CATEGORIES:
        assert category in prompt  # D11 definitions are in the prompt


def test_prompt_is_valid_json_payload_with_truncated_text():
    llm = FakeLLM(_answer_all())
    Classifier(llm, CFG).classify([_item(1, "Hello", text="x" * 5000)])
    payload = read_delimited_items(llm.calls[0][0])
    assert payload[0]["id"] == "id1" and len(payload[0]["text"]) == 1500


def test_llm_noise_and_none_are_accepted():
    llm = FakeLLM(_answer_all(competitor="none", noise=True, category="Customers & Market"))
    (c,) = Classifier(llm, CFG).classify([_item(1, "Unrelated")])
    assert (c.competitor, c.noise, c.category) == ("none", True, "Customers & Market")


@pytest.mark.parametrize("answer", [
    LLMError("timeout"),
    {"nope": 1},
    {"items": "not a list"},
    {"items": []},
    {"items": [{"id": "id1", "competitor": "jfrog", "category": "Security", "noise": False, "confidence": 0.9}]},
    {"items": [{"id": "id1", "competitor": "snyk", "category": "Gossip", "noise": False, "confidence": 0.9}]},
    {"items": [{"id": "id1", "competitor": "snyk", "category": "Security", "noise": "no", "confidence": 0.9}]},
    {"items": [{"id": "id1", "competitor": "snyk", "category": "Security", "noise": False}]},
    {"items": ["garbage", None]},
])
def test_malformed_answer_degrades_to_low_confidence(answer):
    (c,) = Classifier(FakeLLM([answer]), CFG).classify([_item(1, "Some story")])
    assert c.method == "fallback" and c.confidence == LOW_CONFIDENCE
    assert c.degraded and c.needs_review and not c.competitor_confirmed
    assert c.review_reason.startswith("classifier unavailable: ")
    if isinstance(answer, Exception):
        assert c.review_reason == f"classifier unavailable: {type(answer).__name__}"
    assert c.competitor == "snyk" and c.noise is False
    assert "unusable" in c.reason


def test_partial_answer_degrades_only_the_missing_item_and_ignores_invented_ids():
    answer = {"items": [
        {"id": "id1", "competitor": "gitlab", "category": "Security", "noise": False, "confidence": 1.7},
        {"id": "invented", "competitor": "snyk", "category": "Security", "noise": False, "confidence": 0.9},
        {"id": "id1", "competitor": "snyk", "category": "AI & Agents", "noise": True, "confidence": 0.1},
    ]}
    llm = FakeLLM([answer])
    out = Classifier(llm, CFG).classify([_item(1, "Story one"), _item(2, "Story two")])
    assert [c.id for c in out] == ["id1", "id2"]
    assert (out[0].competitor, out[0].category, out[0].confidence) == ("gitlab", "Security", 1.0)  # first wins
    assert (out[1].confidence, out[1].method) == (LOW_CONFIDENCE, "fallback")


def test_schema_restricts_ids_competitors_and_categories():
    schema = Classifier(FakeLLM(), CFG).schema(["a", "b"])
    props = schema["properties"]["items"]["items"]["properties"]
    assert props["id"]["enum"] == ["a", "b"]
    assert props["competitor"]["enum"] == ["snyk", "gitlab", "aws", "industry", "none"]
    assert props["category"]["enum"] == CATEGORIES


# Titles from the Oct 30 run that the first rules settled wrongly; each must now go to the LLM.
@pytest.mark.parametrize("item", [
    _item(1, "GitLab's new 60 req/HR rate limit has a fatal flaw: It blocks the login page", competitor="gitlab"),
    _item(2, "Researchers broke the browsers built into VS Code, Cursor, Copilot, Codex and Claude",
          competitor="gitlab", text="GitLab GitLab GitLab"),
    _item(3, "Octoverse: Commits, pushes, reach new highs in 2026 as developers build with agents",
          competitor="gitlab", source="vendor_feed"),
    _item(4, "PHP2Shell, LiteLLM, GitLab: Find What You Need to Patch", competitor="gitlab", source="hackernews"),
    _item(5, "Shadow AI Across Government: It's Three Problems, Not One", competitor="snyk", source="vendor_feed"),
    _item(6, "Snyk UNFILTERED: Inside Our First-Ever Customer Summit"),
    _item(7, "Snyk vs GitLab: which scanner wins"),
    _item(8, "Agoda consolidates DevSecOps toolchain with GitLab, improving security", competitor="gitlab"),
    _item(9, "Deprecating Trivy vulnerability scanning", source="vendor_feed"),
])
def test_regressions_go_to_the_llm(item):
    result, reason = Classifier(FakeLLM(), CFG).apply_rules(item)
    assert result is None, reason


def test_first_party_or_title_still_settles_clear_items():
    c = Classifier(FakeLLM(), CFG)
    for item, category in [(_item(1, "GitLab patches critical vulnerability that allows code execution",
                                  competitor="gitlab"), "Security"),
                           (_item(2, "Python 3.15 support is now available", source="vendor_feed"),
                            "Product & Features")]:
        result, reason = c.apply_rules(item)
        assert result is not None and result.category == category, reason


@pytest.mark.parametrize("item,first_party", [
    (_item(1, "x", source="vendor_feed"), True),
    (_item(2, "x", source="vendor_feed", origin="https://snyk.io/blog/feed/"), True),  # www. stripped
    (_item(3, "x", source="github_releases"), True),
    (_item(4, "x", source="vendor_feed", origin="https://research.example.com/feed.xml"), False),  # not Snyk's host
    (_item(5, "x", source="vendor_feed", origin="https://about.gitlab.com/atom.xml"), False),  # someone else's feed
    (_item(6, "x", source="github_releases", origin="someone/fork-of-cli"), False),
    (_item(7, "x", source="vendor_feed", competitor="industry", origin=SNYK_FEED), False),  # never for Industry
    (_item(8, "x", source="google_news", origin=SNYK_FEED), False),
])
def test_first_party_only_for_the_competitors_own_feed_or_repo(item, first_party):
    assert Classifier(FakeLLM(), CFG).is_first_party(item) is first_party


def test_a_foreign_feed_does_not_confirm_the_competitor():
    c = Classifier(FakeLLM(), CFG)
    own, _ = c.apply_rules(_item(1, "Python 3.15 support is now available", source="vendor_feed"))
    foreign, why = c.apply_rules(_item(1, "Python 3.15 support is now available", source="vendor_feed",
                                       origin="https://research.example.com/feed.xml"))
    assert own is not None and foreign is None and "not a first-party source" in why
    industry, _ = c.apply_rules(_item(1, "Python 3.15 support is now available", source="vendor_feed",
                                      competitor="industry"))
    assert industry is None


def test_rules_work_with_a_single_tracked_competitor():
    solo = CIConfig(competitors=[Competitor(key="snyk", name="Snyk"), Competitor(key="industry", name="Industry")])
    result, reason = Classifier(FakeLLM(), solo).apply_rules(_item(1, "Snyk patches critical vulnerability"))
    assert result is not None and result.category == "Security", reason
    only = CIConfig(competitors=[Competitor(key="snyk", name="Snyk")])
    assert Classifier(FakeLLM(), only).apply_rules(_item(2, "Snyk on a quiet Tuesday"))[0] is None


def _with_mentions(item, mentions, jfrog=False):
    return {**item, "mentions": {"snyk": 0, "gitlab": 0, "aws": 0, **mentions}, "mentions_jfrog": jfrog}


def test_full_page_mentions_drive_dominance():
    c = Classifier(FakeLLM(), CFG)
    item = _item(1, "Snyk patches critical vulnerability", text="Snyk short teaser")
    assert c.apply_rules(item)[0] is not None  # stored text: Snyk only
    result, why = c.apply_rules(_with_mentions(item, {"snyk": 2, "gitlab": 9}))  # the full page is about GitLab
    assert result is None and "GitLab dominates" in why


def test_without_mentions_the_classifier_counts_the_stored_text():
    c = Classifier(FakeLLM(), CFG)
    item = _item(1, "Snyk patches critical vulnerability", text="GitLab GitLab GitLab GitLab")
    result, why = c.apply_rules(item)
    assert result is None and "GitLab dominates (4 vs 3)" in why


def test_full_page_jfrog_flag_is_used():
    llm = FakeLLM(_answer_all())
    plain = _item(1, "Top 5 SCA tools", text="no vendor named here")
    (a, b) = Classifier(llm, CFG).classify([plain, _with_mentions({**plain, "id": "id2"}, {"snyk": 1}, jfrog=True)])
    assert (a.mentions_jfrog, b.mentions_jfrog) == (False, True)


def test_full_text_mentions_hint_reaches_the_llm():
    llm = FakeLLM(_answer_all())
    items = [_with_mentions(_item(1, "Top 5 SCA tools", competitor="industry"), {"aws": 3, "snyk": 1}),
             _item(2, "Another list", competitor="industry")]
    Classifier(llm, CFG).classify(items)
    payload = read_delimited_items(llm.calls[0][0])
    assert payload[0]["full_text_mentions"] == "aws×3, snyk×1"
    assert "full_text_mentions" not in payload[1]
    assert "full_text_mentions" in llm.calls[0][0].split("\nItems:\n")[0]  # explained in the instructions


@pytest.mark.parametrize("title,text", [
    ("Snyk patches critical vulnerability", "Snyk said GitLab and Snyk agree. Snyk!"),
    ("GitLab and Snyk ship", "AWS CodeArtifact and CodeArtifact, then GitLab"),
    ("Nothing named", "plain text"),
])
def test_weights_are_identical_with_and_without_stored_mentions(title, text):
    from ci.classify import MentionCounter

    c = Classifier(FakeLLM(), CFG)
    item = _item(1, title, text=text)
    counts, _ = MentionCounter(CFG)(text)
    assert c._mention_weights({**item, "mentions": counts}) == c._mention_weights(item)


@pytest.mark.parametrize("text,expected", [
    ("see https://github.com/snyk/cli for details", 0),
    ("clone github.com/gitlab-org/gitlab and snyk.io/docs", 0),
    ("read about.gitlab.com/blog and www.snyk.io", 0),
    ("Snyk and GitLab compared; source on https://gitlab.com/x", 2),
])
def test_urls_are_not_mentions(text, expected):
    from ci.classify import MentionCounter

    counts, jfrog = MentionCounter(CFG)(text + " https://jfrog.com/artifactory/")
    assert sum(counts.values()) == expected and jfrog is False


def test_stale_stored_counts_never_zero_a_competitor():
    c = Classifier(FakeLLM(), CFG)
    # counts taken before aws was tracked: the key is missing, but the stored text names it
    item = {**_item(1, "x", text="CodeArtifact and CodeArtifact, Snyk"), "mentions": {"snyk": 4, "gitlab": 1}}
    assert c.text_counts(item) == {"snyk": 4, "gitlab": 1, "aws": 2}


def test_mention_config_hash_tracks_the_name_rules():
    from ci.classify import MentionCounter

    other = CIConfig(competitors=[*CFG.competitors, Competitor(key="cloudsmith", name="Cloudsmith")])
    assert MentionCounter(CFG).config_hash == MentionCounter(CFG).config_hash != MentionCounter(other).config_hash


def test_junk_text_never_reaches_the_llm_or_the_mention_counts():
    junk = {**_item(1, "Some story about tools", competitor="industry",
                    text="NAVMENU GitLab GitLab GitLab JFrog Snyk Snyk"), "text_status": "junk",
            "teaser": "A teaser naming Snyk once."}
    llm = FakeLLM(_answer_all())
    c = Classifier(llm, CFG)
    assert c.text_counts(junk)["gitlab"] == 0 and c.text_counts(junk)["snyk"] == 1
    (out,) = c.classify([junk])
    prompt = llm.calls[0][0]
    assert "NAVMENU" not in prompt and "A teaser naming Snyk once." in prompt
    assert out.mentions_jfrog is False  # "JFrog" was only in the junk text


GH_CFG = CIConfig(competitors=[Competitor(key="github", name="GitHub"), Competitor(key="gitlab", name="GitLab"),
                               Competitor(key="snyk", name="Snyk"), Competitor(key="industry", name="Industry")])


def _industry(title, text="x" * 92):
    return {"id": "i1", "title": title, "competitor": "industry", "text": text, "source": "google_news",
            "origin": "q", "text_status": "snippet"}


def test_an_industry_item_whose_title_names_github_is_tagged_github():
    item = _industry("GitHub Launches npm Firewall to Block Malicious Packages Before Installation",
                     "GitHub launched an npm firewall that blocks malicious packages before they get installed now")
    assert len(item["text"]) == 92
    llm = FakeLLM(_answer_all(competitor="industry", category="Security"))  # the LLM would keep industry
    (c,) = Classifier(llm, GH_CFG, runs_dir=None).classify([item])
    assert c.competitor == "github" and c.reason.startswith("title names github")
    assert c.category == "Security" and c.method == "llm"  # category and noise still come from rules/LLM
    payload = read_delimited_items(llm.calls[0][0])
    assert payload[0]["prefilled_competitor"] == "github"


def test_an_industry_title_naming_nobody_stays_industry():
    llm = FakeLLM(_answer_all(competitor="industry"))
    (c,) = Classifier(llm, GH_CFG, runs_dir=None).classify([_industry("Malicious npm packages steal tokens")])
    assert c.competitor == "industry" and not c.reason.startswith("title names")


def test_an_industry_title_naming_two_competitors_goes_to_the_llm():
    clf = Classifier(FakeLLM(_answer_all(competitor="gitlab")), GH_CFG, runs_dir=None)
    item = _industry("GitHub and GitLab both patch CI runner flaws")
    assert clf.title_competitor(item) is None
    (c,) = clf.classify([item])
    assert c.competitor == "gitlab" and c.method == "llm" and not c.reason.startswith("title names")


def test_market_chatter_naming_gitlab_is_not_settled_by_the_title():
    clf = Classifier(FakeLLM(_answer_all(competitor="none", noise=True)), GH_CFG, runs_dir=None)
    item = _industry("GitLab stock rallies after earnings beat")
    assert clf.title_competitor(item) is None
    (c,) = clf.classify([item])
    assert c.competitor == "none" and c.noise  # left to the LLM


def test_a_title_named_competitor_can_be_settled_by_the_rules_too():
    (c,) = Classifier(FakeLLM(), GH_CFG, runs_dir=None).classify([_industry("Snyk patches critical vulnerability")])
    assert (c.competitor, c.method, c.category) == ("snyk", "rules", "Security")
    assert c.reason.startswith("title names snyk")


def _payload(llm) -> list[dict]:
    return read_delimited_items(llm.calls[0][0])


@pytest.mark.parametrize("title", [
    "GitHub Launches npm Firewall to Block Malicious Packages Before Installation",
    "GitHub's npm package firewall can block brand-new versions",
    "GitHub’s npm package firewall can block brand-new versions",  # typographic apostrophe
    "Exclusive: GitHub rolls out an npm firewall",
    "GitHub unveiled its npm firewall",
])
def test_competitor_as_the_title_subject_is_settled_by_rule(title):
    clf = Classifier(FakeLLM(_answer_all(competitor="industry")), GH_CFG, runs_dir=None)
    item = _industry(title)
    assert item["text_status"] == "snippet" and clf.title_competitor(item) == "github"
    (c,) = clf.classify([item])
    assert c.competitor == "github" and c.reason.startswith("title names github")


def test_competitor_named_only_as_a_venue_goes_to_the_llm_with_the_hint_and_stays_industry():
    llm = FakeLLM(_answer_all(competitor="industry"))
    clf = Classifier(llm, GH_CFG, runs_dir=None)
    item = _industry("Hackers Hide Malware in 42 GitHub Repositories")
    assert clf.title_competitor(item) is None and clf.title_named(item) == "github"
    (c,) = clf.classify([item])
    assert c.competitor == "industry" and c.method == "llm" and not c.reason.startswith("title names")
    prompt = llm.calls[0][0]
    assert "Competitor named in title: github — company or platform?" in prompt
    [sent] = _payload(llm)
    assert sent["prefilled_competitor"] == "industry"
    assert sent["hint"] == "Competitor named in title: github — company or platform?"


def test_a_title_led_by_the_name_without_a_verb_gets_the_hint():
    llm = FakeLLM(_answer_all(competitor="github"))
    (c,) = Classifier(llm, GH_CFG, runs_dir=None).classify(
        [_industry("GitHub Supply Chain Attack: Command Injection in Actions workflows")])
    assert _payload(llm)[0]["hint"] == "Competitor named in title: github — company or platform?"
    assert c.competitor == "github" and c.method == "llm"  # the LLM may still decide it is about GitHub


def test_hinted_item_falls_back_to_industry_when_the_llm_fails():
    llm = FakeLLM([RuntimeError("down")])
    (c,) = Classifier(llm, GH_CFG, runs_dir=None).classify([_industry("Malware found in GitHub Repositories")])
    assert c.competitor == "industry" and c.degraded


def test_no_hint_without_a_named_competitor_or_with_two():
    llm = FakeLLM(_answer_all())
    Classifier(llm, GH_CFG, runs_dir=None).classify([
        {**_industry("Malicious npm packages steal tokens"), "id": "a"},
        {**_industry("Malware spreads via GitHub and GitLab runners"), "id": "b"},
        {**_industry("GitLab stock rallies after earnings beat"), "id": "c"}])  # chatter guard still wins
    assert all("hint" not in row for row in _payload(llm))


HINT = "Competitor named in title: github — company or platform?"


@pytest.mark.parametrize("title,expected", [
    ("GitHub’s repositories abused to host malware", "hint"),  # a venue after the possessive
    ("GitHub's repositories abused to host malware", "hint"),
    ("GitHub made headlines after malware found in repos", "hint"),  # weak verb
    ("GitHub brings bad news for maintainers", "hint"),
    ("GitHub updates: attackers abuse workflow triggers", "hint"),  # a heading, not a verb
    ("GitHub's users targeted by phishing", "hint"),
    ("GitHub's new policy angers maintainers", "hint"),  # anything else after 's never settles by default
    ("GitHub’s npm registry hit by worm", "hint"),  # a generic word (npm, registry) is a venue, not a product
    ("GitHub's AI agents leak tokens", "hint"),
    ("GitHub's MCP server exposed", "hint"),
    ("GitHub's Dependabot gets reachability", "github"),
    ("GitHub's npm firewall can block brand-new versions", "github"),
    ("GitHub’s Copilot gets a security review mode", "github"),
    ("GitHub's Advanced Security adds AI autofix", "github"),
    ("GitHub Launches npm Firewall to Block Malicious Packages Before Installation", "github"),
    ("Hackers Hide Malware in 42 GitHub Repositories", "hint"),
])
def test_reviewer_title_examples(title, expected):
    llm = FakeLLM(_answer_all(competitor="industry"))
    clf = Classifier(llm, GH_CFG, runs_dir=None)
    item = _industry(title)
    (c,) = clf.classify([item])
    if expected == "github":
        assert clf.title_competitor(item) == "github" and c.competitor == "github"
        assert c.reason.startswith("title names github")
    else:
        assert clf.title_competitor(item) is None and c.competitor == "industry" and c.method == "llm"
        assert _payload(llm)[0]["hint"] == HINT
