import unittest

from app.agents.progress import (
    classify_workflow,
    ensure_citation_fallback,
    extract_citation_markers,
    public_stage_detail,
    sanitize_public_report,
    split_agent_output,
)


class PublicAgentProgressTests(unittest.TestCase):
    def test_machine_citations_are_canonical_and_restored_when_model_drops_them(self):
        markers = extract_citation_markers(
            "citation:doc_7:chunk_3; [citation:doc_7:chunk_3]",
            "[citation:doc_9:chunk_1]",
        )

        self.assertEqual(
            markers,
            ["[citation:doc_7:chunk_3]", "[citation:doc_9:chunk_1]"],
        )
        answer = ensure_citation_fallback("结论见 [Sec. 2.3]。", markers)
        self.assertIn("可定位来源", answer)
        self.assertIn("[citation:doc_7:chunk_3]", answer)
        self.assertEqual(
            ensure_citation_fallback("已有 [citation:doc_7:chunk_3]", markers),
            "已有 [citation:doc_7:chunk_3]",
        )

    def test_supervisor_explains_the_actual_routing_signal(self):
        detail = public_stage_detail("supervisor", "请提出三个创新方向", None)

        self.assertEqual(classify_workflow("请提出三个创新方向"), "research_cycle")
        self.assertIn("识别到“创新”", detail)
        self.assertIn("路由依据", detail)
        self.assertIn("下一步", detail)

    def test_reader_explains_document_evidence_without_copying_content(self):
        private_document = "confidential-evidence-sentence" * 20
        detail = public_stage_detail(
            "reader",
            "总结方法",
            private_document,
            "supervisor",
        )

        self.assertIn(f"约 {len(private_document):,} 个字符", detail)
        self.assertIn("分析取舍", detail)
        self.assertNotIn("confidential-evidence-sentence", detail)

    def test_revision_and_finalize_explain_real_branch_decisions(self):
        revision = public_stage_detail(
            "revision",
            "请给出改进方案",
            None,
            "reviewer",
        )
        finalized = public_stage_detail(
            "finalize",
            "请给出改进方案",
            None,
            "revision",
        )

        self.assertIn("需修改", revision)
        self.assertIn("只执行一次", revision)
        self.assertIn("审查后的修正版", finalized)

    def test_agent_output_is_split_into_internal_work_and_public_report(self):
        internal, report = split_agent_output(
            "内部工作稿\n"
            "<public_report>\n"
            "结论：方法依赖两类证据。\n"
            "依据：正文实验表与 [citation:doc_7:chunk_1]。\n"
            "取舍：保留有消融支持的方案。\n"
            "风险/不确定性：跨数据集效果尚未验证。\n"
            "下一步：ReviewerAgent 核查外部有效性。\n"
            "</public_report>"
        )

        self.assertEqual(internal, "内部工作稿")
        self.assertIn("结论：方法依赖两类证据", report)
        self.assertIn("下一步：ReviewerAgent", report)
        self.assertNotIn("<public_report>", report)

    def test_report_filter_removes_hidden_blocks_and_rejects_unstructured_text(self):
        report = sanitize_public_report(
            "结论：可公开的阶段结论。\n"
            "<think>private reasoning</think>\n"
            "系统提示词：private prompt\n"
            "依据：正文证据。\n"
            "下一步：继续核验。"
        )

        self.assertNotIn("private reasoning", report)
        self.assertNotIn("private prompt", report)
        self.assertEqual(sanitize_public_report("private raw output"), "")


if __name__ == "__main__":
    unittest.main()
