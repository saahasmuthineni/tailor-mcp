"""
Tests for vault/parser.py — pure-function wikilink, tag, and frontmatter parsing.
"""

from biosensor_mcp.framework.vault.parser import (
    extract_tags,
    extract_wikilinks,
    resolve_link,
    split_frontmatter,
)


class TestExtractWikilinks:
    def test_simple_wikilink(self):
        links = extract_wikilinks("See [[foo]] for details.")
        assert links == [("foo", "foo")]

    def test_wikilink_with_display_text(self):
        links = extract_wikilinks("See [[foo|Nice Foo]] for details.")
        assert links == [("foo", "Nice Foo")]

    def test_multiple_wikilinks(self):
        links = extract_wikilinks("[[a]] and [[b|B!]] and [[c]]")
        assert links == [("a", "a"), ("b", "B!"), ("c", "c")]

    def test_no_wikilinks(self):
        assert extract_wikilinks("no links here") == []

    def test_wikilinks_in_fenced_code_ignored(self):
        body = "Visible [[outside]]\n```\n[[inside-code]]\n```\nAlso [[end]]"
        links = extract_wikilinks(body)
        targets = [t for (t, _) in links]
        assert "outside" in targets
        assert "end" in targets
        assert "inside-code" not in targets

    def test_tilde_fences_also_respected(self):
        body = "[[out]]\n~~~\n[[skipped]]\n~~~"
        targets = [t for (t, _) in extract_wikilinks(body)]
        assert "out" in targets
        assert "skipped" not in targets

    def test_unicode_target(self):
        links = extract_wikilinks("[[café-notes]]")
        assert links == [("café-notes", "café-notes")]

    def test_empty_target_ignored(self):
        assert extract_wikilinks("[[]]") == []


class TestExtractTags:
    def test_single_tag(self):
        assert extract_tags("a #hello b") == ["hello"]

    def test_nested_tag(self):
        assert extract_tags("tagged #aerobic/decoupled run") == ["aerobic/decoupled"]

    def test_multiple_tags(self):
        assert extract_tags("#one and #two and #three") == ["one", "two", "three"]

    def test_tags_inside_fenced_code_ignored(self):
        body = "#visible\n```\n#hidden\n```\n#also-visible"
        assert extract_tags(body) == ["visible", "also-visible"]

    def test_tags_inside_inline_code_ignored(self):
        assert extract_tags("Use `#inline` tag, not #real") == ["real"]

    def test_numeric_suffix_not_a_tag(self):
        # "#123" has no leading letter — our regex requires one.
        assert extract_tags("issue #123 referenced") == []

    def test_hashtag_without_word_boundary_skipped(self):
        # Inside a word-character run (e.g. URLs) — the regex uses a
        # negative lookbehind to avoid matching.
        assert extract_tags("abc#def") == []


class TestSplitFrontmatter:
    def test_simple_frontmatter(self):
        content = '---\ntitle: "X"\nstatus: open\n---\nbody here'
        fm, body = split_frontmatter(content)
        assert fm["title"] == "X"
        assert fm["status"] == "open"
        assert body == "body here"

    def test_no_frontmatter(self):
        fm, body = split_frontmatter("just body")
        assert fm == {}
        assert body == "just body"

    def test_flow_list(self):
        content = '---\ntags: ["a", "b", "c"]\n---\nbody'
        fm, _ = split_frontmatter(content)
        assert fm["tags"] == ["a", "b", "c"]

    def test_block_list(self):
        content = "---\ntags:\n  - first\n  - second\n---\nbody"
        fm, _ = split_frontmatter(content)
        assert fm["tags"] == ["first", "second"]

    def test_scalar_types(self):
        content = '---\nyes_flag: true\nno_flag: false\ncount: 42\nrate: 3.14\n---\nbody'
        fm, _ = split_frontmatter(content)
        assert fm["yes_flag"] is True
        assert fm["no_flag"] is False
        assert fm["count"] == 42
        assert fm["rate"] == 3.14

    def test_body_with_multiple_dashes(self):
        content = '---\ntitle: "T"\n---\n\n# body\n---\nnot a delimiter\n'
        fm, body = split_frontmatter(content)
        assert fm["title"] == "T"
        assert "not a delimiter" in body


class TestResolveLink:
    def test_direct_stem_match(self):
        known = {"themes/foo.md", "running/2025-04-10-activity-12345.md"}
        assert resolve_link("foo", known) == "themes/foo.md"

    def test_case_insensitive(self):
        known = {"themes/Dehydration-Drift.md"}
        assert resolve_link("dehydration-drift", known) == "themes/Dehydration-Drift.md"

    def test_suffix_match_for_activity(self):
        known = {"running/2025-04-10-activity-12345.md"}
        assert resolve_link("activity-12345", known) == "running/2025-04-10-activity-12345.md"

    def test_md_extension_stripped(self):
        known = {"themes/foo.md"}
        assert resolve_link("foo.md", known) == "themes/foo.md"

    def test_unresolvable_returns_none(self):
        known = {"themes/foo.md"}
        assert resolve_link("nonexistent", known) is None

    def test_empty_target(self):
        assert resolve_link("", {"themes/foo.md"}) is None
