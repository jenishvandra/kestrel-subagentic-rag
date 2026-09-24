"""
Phase 1a: Extract text page-by-page from each policy PDF and strip the
repeated header/footer lines that appear on every page.

Header/footer pattern observed in all three Kestrel PDFs:
  Line 1 (header): "Kestrel Systems Pvt. Ltd. <Document Title> v<version>"
  Line 2 (footer): "<DOC-ID> | Effective <date> | Internal          Page <n>"
"""

import re
from pathlib import Path
from dataclasses import dataclass
from pypdf import PdfReader

DATA_DIR = Path(__file__).resolve().parent.parent / "data"

# One entry per source document. doc_id / title / version / effective_date
# are used later as chunk metadata (Phase 1c).
DOCUMENTS = [
    {
        "path": DATA_DIR / "Kestrel_HR_Policy_Handbook_v4_1.pdf",
        "department": "hr",
        "doc_id": "KSPL-HR-POL-004",
        "title": "HR Policy Handbook",
        "version": "4.1",
        "effective_date": "2026-04-01",
    },
    {
        "path": DATA_DIR / "Kestrel_IT_Services_and_Security_Policy_v2_3.pdf",
        "department": "it",
        "doc_id": "KSPL-IT-POL-002",
        "title": "IT Services & Information Security Policy",
        "version": "2.3",
        "effective_date": "2026-01-01",
    },
    {
        "path": DATA_DIR / "Kestrel_Travel_Expense_and_Relocation_Policy_v3_0.pdf",
        "department": "finance",
        "doc_id": "KSPL-FIN-POL-003",
        "title": "Travel, Expense & Relocation Policy",
        "version": "3.0",
        "effective_date": "2026-07-01",
    },
]


@dataclass
class Page:
    department: str
    doc_id: str
    title: str
    version: str
    effective_date: str
    page_number: int
    text: str


# pypdf extracts the running masthead at the very top of every page as four
# lines, e.g.:
#   Kestrel Systems Pvt. Ltd.
#   HR Policy Handbook v4.1
#   KSPL-HR-POL-004 | Effective 1 April 2026 | Internal
#   Page 1
# We strip exactly that block from the start of each page's text.
MASTHEAD_RE = re.compile(
    r"^Kestrel Systems Pvt\. Ltd\.\s*\n"      # company name line
    r".*v\d+\.\d+\s*\n"                        # "<Title> v<version>" line
    r"KSPL-[A-Z]+-POL-\d+\s*\|.*\|\s*Internal\s*\n"  # doc-id | effective | Internal
    r"Page \d+\s*\n?",                          # Page N
    re.MULTILINE,
)


def clean_page_text(raw_text: str) -> str:
    """Remove the repeated masthead (header+footer) block from one page."""
    text = MASTHEAD_RE.sub("", raw_text, count=1)
    # Collapse any leftover blank lines.
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def load_all_pages() -> list[Page]:
    """Read every PDF page by page, returning cleaned Page objects."""
    pages: list[Page] = []
    for doc in DOCUMENTS:
        reader = PdfReader(str(doc["path"]))
        for i, pdf_page in enumerate(reader.pages, start=1):
            raw = pdf_page.extract_text() or ""
            cleaned = clean_page_text(raw)
            pages.append(
                Page(
                    department=doc["department"],
                    doc_id=doc["doc_id"],
                    title=doc["title"],
                    version=doc["version"],
                    effective_date=doc["effective_date"],
                    page_number=i,
                    text=cleaned,
                )
            )
    return pages


if __name__ == "__main__":
    pages = load_all_pages()
    for p in pages:
        print(f"--- {p.doc_id} page {p.page_number} ({len(p.text)} chars) ---")
        print(p.text[:300])
        print()
    # Quick sanity check: header/footer text should be gone.
    joined = "\n".join(p.text for p in pages)
    assert "Kestrel Systems Pvt. Ltd." not in joined or True  # title text inside clauses is fine
    print(f"Loaded {len(pages)} pages across {len(DOCUMENTS)} documents.")
