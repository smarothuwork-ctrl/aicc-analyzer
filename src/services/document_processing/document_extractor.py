from __future__ import annotations


class DocumentExtractor:
    def extract_text(self, document_url: str) -> str:
        if not document_url:
            return ""
        return f"Extracted text from document: {document_url}"
