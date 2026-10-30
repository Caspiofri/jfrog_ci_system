"""The shared contract: config loads, packet ids are stable."""
from ci import config
from ci.packet import INDUSTRY, Packet, packet_id


def test_competitors_config_loads():
    cfg = config.load()
    keys = cfg.by_key()
    assert {"cloudsmith", "sonatype", "github", "gitlab", "snyk", "aws_codeartifact", INDUSTRY} == set(keys)
    assert all(c.news_queries for c in cfg.competitors)
    assert cfg.window_days == 7


def test_packet_id_is_stable_and_url_based():
    assert packet_id("https://a.com/x") == packet_id("https://a.com/x")
    assert packet_id("https://a.com/x") != packet_id("https://a.com/y")


def test_packet_defaults():
    p = Packet(source="hackernews", origin="Snyk", competitor="snyk", title="t", url="u", original_url="u")
    assert p.url_resolved and p.text_status == "snippet" and p.id == "" and not p.in_24h
