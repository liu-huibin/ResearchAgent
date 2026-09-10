import unittest

from app.models.document import Document
from app.services.chat.service import format_citable_document_context


class CitableDocumentContextTests(unittest.TestCase):
    def test_session_document_context_contains_machine_location_markers(self):
        document = Document(id=7, filename="paper.pdf", file_path="paper.pdf")

        context = format_citable_document_context(
            document,
            "第一段论文内容。\n\n第二段论文内容。",
        )

        self.assertIn("第一段论文内容", context)
        self.assertIn("[citation:doc_7:chunk_0]", context)


if __name__ == "__main__":
    unittest.main()
