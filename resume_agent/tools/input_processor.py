from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Tuple


@dataclass
class InputPayload:
    source_path: Optional[Path]
    raw_text: Optional[str]


class InputProcessor:
    """Convert text/PDF/Word input to markdown."""

    def run(self, payload: InputPayload) -> Tuple[str, str]:
        if payload.raw_text:
            markdown = self._normalize_text(payload.raw_text)
            return markdown, "text"

        if not payload.source_path:
            raise ValueError("Either raw_text or source_path must be provided.")

        path = payload.source_path
        if not path.exists():
            raise FileNotFoundError(f"Input file not found: {path}")

        ext = path.suffix.lower()
        if ext in (".txt", ".md"):
            return self._normalize_text(path.read_text(encoding="utf-8")), ext
        if ext == ".pdf":
            return self._read_pdf(path), ext
        if ext in (".docx", ".doc"):
            return self._read_docx(path), ext

        raise ValueError(f"Unsupported input format: {ext}")

    def _normalize_text(self, text: str) -> str:
        normalized = text.replace("\r\n", "\n").strip()
        if not normalized:
            raise ValueError("Input text is empty after normalization.")
        return normalized

    def _read_pdf(self, path: Path) -> str:
        try:
            import pdfplumber  # type: ignore
        except Exception as exc:
            raise RuntimeError("pdfplumber is required to read PDF files.") from exc

        pieces = []
        with pdfplumber.open(str(path)) as pdf:
            for page in pdf.pages:
                text = page.extract_text() or ""
                pieces.append(text)
        return self._normalize_text("\n".join(pieces))

    def _read_docx(self, path: Path) -> str:
        try:
            import docx  # type: ignore
        except Exception as exc:
            raise RuntimeError("python-docx is required to read Word files.") from exc

        doc = docx.Document(str(path))
        parts = [p.text for p in doc.paragraphs if p.text.strip()]
        return self._normalize_text("\n".join(parts))
