from notex.core.syntax import (STATE_BLOCK_COMMENT, STATE_FENCE_LANG_BASE, STATE_NONE, STATE_TRIPLE_DQ, FENCE_LANGS,
                               lex_line, lex_log_line, lexer_for_extension)


def styles(text, lexer, state=STATE_NONE):
    spans, new_state = lex_line(text, lexer, state)
    return [(text[s.start:s.end], s.style) for s in spans], new_state


def test_extension_mapping() -> None:
    assert lexer_for_extension(".py") == "python" and lexer_for_extension(".YML") == "yaml"
    assert lexer_for_extension(".txt") is None


def test_python_tokens_and_docstring_state() -> None:
    spans, state = styles("def add(a, b):  # summe", "python")
    assert ("def", "keyword") in spans and ("add", "function") in spans and ("# summe", "comment") in spans
    assert state == STATE_NONE
    spans, state = styles('x = """anfang', "python")
    assert state == STATE_TRIPLE_DQ and ("\"\"\"anfang", "string") in spans
    spans, state = styles("mitte", "python", STATE_TRIPLE_DQ)
    assert spans == [("mitte", "string")] and state == STATE_TRIPLE_DQ
    spans, state = styles('ende"""', "python", STATE_TRIPLE_DQ)
    assert state == STATE_NONE and spans[0][1] == "string"


def test_block_comment_state_for_js() -> None:
    _, state = styles("let a = 1; /* offen", "javascript")
    assert state == STATE_BLOCK_COMMENT
    spans, state = styles("noch */ let b = 2;", "javascript", STATE_BLOCK_COMMENT)
    assert state == STATE_NONE and spans[0] == ("noch */", "comment")


def test_markdown_fence_uses_language_lexer() -> None:
    spans, state = styles("```python", "markdown")
    assert state == STATE_FENCE_LANG_BASE + FENCE_LANGS.index("python")
    spans, state2 = styles("import os", "markdown", state)
    assert ("import", "keyword") in spans and state2 == state
    spans, state3 = styles("```", "markdown", state)
    assert state3 == STATE_NONE
    spans, _ = styles("# Titel", "markdown")
    assert spans and spans[0][1] == "keyword"


def test_log_lines() -> None:
    spans = lex_log_line("2026-09-26 10:00:01 ERROR client 192.168.1.10:443 failed /var/log/app.log")
    kinds = {s.style for s in spans}
    assert {"log_time", "log_error", "log_ip", "log_path"} <= kinds
    assert lex_log_line("DEBUG only")[0].style == "log_debug"
    assert lex_log_line("plain text") == []


def test_unknown_lexer_is_harmless() -> None:
    assert lex_line("x", None) == ([], STATE_NONE)
    assert lex_line("x", "gibtsnicht") == ([], STATE_NONE)
