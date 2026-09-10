import unittest

from app.services.sessions.titles import generate_session_title, is_placeholder_title


class SessionTitleTests(unittest.TestCase):
    def test_title_uses_first_meaningful_clause_and_is_very_short(self):
        title = generate_session_title("请帮我总结这篇论文的方法和实验结果，并提出建议")

        self.assertEqual(title, "总结这篇论文的方法和实验")
        self.assertLessEqual(len(title), 12)

    def test_title_removes_links_markdown_and_replaces_placeholder_on_fallback(self):
        self.assertEqual(
            generate_session_title("我希望分析 [研究论文](https://example.com/paper) 的贡献"),
            "分析研究论文的贡献",
        )
        self.assertEqual(generate_session_title("https://example.com"), "链接内容分析")
        self.assertEqual(generate_session_title("[citation:doc_7:chunk_1]"), "引用内容分析")
        self.assertEqual(generate_session_title("   "), "会话内容")

    def test_only_placeholder_titles_are_eligible_for_automatic_replacement(self):
        self.assertTrue(is_placeholder_title("新会话"))
        self.assertTrue(is_placeholder_title("New Chat"))
        self.assertFalse(is_placeholder_title("联邦学习实验"))


if __name__ == "__main__":
    unittest.main()
