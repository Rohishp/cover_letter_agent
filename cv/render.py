from pathlib import Path

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Inches, Mm, Pt, RGBColor

from cv.schema import BaseEntry, CVContent, Certification, Language, SkillGroup


FONT_NAME = "Calibri"
BODY_SIZE = Pt(10)
HEADING_SIZE = Pt(12)

DARK_CHARCOAL = RGBColor(0x33, 0x33, 0x33)
DARK_NAVY = RGBColor(0x1B, 0x2A, 0x4A)
ACCENT = RGBColor(0x2E, 0x74, 0xB5)
ACCENT_HEX = "2E74B5"

MARGIN = Inches(0.7)


def _add_run(
    paragraph,
    text: str,
    *,
    bold: bool = False,
    size=BODY_SIZE,
    color: RGBColor = DARK_CHARCOAL,
):
    run = paragraph.add_run(text)
    run.font.name = FONT_NAME
    run.font.size = size
    run.font.bold = bold
    run.font.color.rgb = color
    return run


def _add_bottom_border(paragraph, color_hex: str, size_eighths_pt: int = 6) -> None:
    p_pr = paragraph._p.get_or_add_pPr()
    p_bdr = OxmlElement("w:pBdr")
    bottom = OxmlElement("w:bottom")
    bottom.set(qn("w:val"), "single")
    bottom.set(qn("w:sz"), str(size_eighths_pt))
    bottom.set(qn("w:space"), "4")
    bottom.set(qn("w:color"), color_hex)
    p_bdr.append(bottom)
    p_pr.append(p_bdr)


def _add_section_heading(doc: Document, text: str):
    para = doc.add_paragraph()
    para.alignment = WD_ALIGN_PARAGRAPH.LEFT
    para.paragraph_format.space_before = Pt(14)
    para.paragraph_format.space_after = Pt(6)
    _add_run(para, text, bold=True, size=HEADING_SIZE, color=DARK_NAVY)
    _add_bottom_border(para, ACCENT_HEX)
    return para


def _add_bullet(doc: Document, text: str, space_after=Pt(2)):
    para = doc.add_paragraph(style="List Bullet")
    para.paragraph_format.space_before = Pt(0)
    para.paragraph_format.space_after = space_after
    _add_run(para, text)
    return para


def _add_header_block(doc: Document, content: CVContent) -> None:
    name_para = doc.add_paragraph()
    name_para.alignment = WD_ALIGN_PARAGRAPH.CENTER
    name_para.paragraph_format.space_after = Pt(2)
    _add_run(name_para, content.full_name, bold=True, size=HEADING_SIZE, color=DARK_NAVY)

    title_para = doc.add_paragraph()
    title_para.alignment = WD_ALIGN_PARAGRAPH.CENTER
    title_para.paragraph_format.space_after = Pt(2)
    _add_run(title_para, content.target_title)

    contact_line = " | ".join([content.location, *content.contact_lines])
    contact_para = doc.add_paragraph()
    contact_para.alignment = WD_ALIGN_PARAGRAPH.CENTER
    contact_para.paragraph_format.space_after = Pt(10)
    _add_run(contact_para, contact_line)


def _add_entry(doc: Document, entry: BaseEntry) -> None:
    row1 = doc.add_paragraph()
    row1.paragraph_format.space_before = Pt(8)
    row1.paragraph_format.space_after = Pt(0)
    _add_run(row1, entry.position, bold=True)

    org_and_city = (
        f"{entry.organisation}, {entry.city}" if entry.city else entry.organisation
    )
    _add_run(row1, f" | {org_and_city} | {entry.dates}")

    if entry.tools:
        tools_para = doc.add_paragraph()
        tools_para.paragraph_format.space_before = Pt(0)
        tools_para.paragraph_format.space_after = Pt(0)
        _add_run(tools_para, f"Tools: {entry.tools}")

    if entry.topic:
        topic_para = doc.add_paragraph()
        topic_para.paragraph_format.space_before = Pt(0)
        topic_para.paragraph_format.space_after = Pt(2)
        _add_run(topic_para, entry.topic, bold=True)

    bullet_count = len(entry.bullets)

    for index, bullet_text in enumerate(entry.bullets):
        is_last = index == bullet_count - 1
        _add_bullet(doc, bullet_text, space_after=Pt(6) if is_last else Pt(2))


def _add_skill_group(doc: Document, group: SkillGroup) -> None:
    para = doc.add_paragraph()
    para.paragraph_format.space_after = Pt(4)
    _add_run(para, f"{group.name}: ", bold=True)
    _add_run(para, ", ".join(group.items))


def _add_certification(doc: Document, cert: Certification) -> None:
    para = doc.add_paragraph()
    para.paragraph_format.space_after = Pt(4)
    _add_run(para, cert.name, bold=True)

    detail = f" | {cert.issuer} | {cert.issued}"

    if cert.expires:
        detail += f" to {cert.expires}"

    _add_run(para, detail)


def _add_language(doc: Document, language: Language) -> None:
    para = doc.add_paragraph()
    para.paragraph_format.space_after = Pt(4)
    _add_run(para, f"{language.language}: ", bold=True)
    _add_run(para, language.level)


def _set_default_style(doc: Document) -> None:
    normal = doc.styles["Normal"]
    normal.font.name = FONT_NAME
    normal.font.size = BODY_SIZE


def render_cv(content: CVContent, out_path: Path) -> Path:
    """
    Render CVContent to a .docx file.

    Owns every formatting rule. Deterministic: same content in, same
    document out, every time.
    """

    doc = Document()

    section = doc.sections[0]
    section.page_width = Mm(210)
    section.page_height = Mm(297)
    section.left_margin = MARGIN
    section.right_margin = MARGIN
    section.top_margin = MARGIN
    section.bottom_margin = MARGIN

    _set_default_style(doc)

    _add_header_block(doc, content)

    if content.profile:
        _add_section_heading(doc, "Profile")

        profile_para = doc.add_paragraph()
        profile_para.paragraph_format.space_after = Pt(6)
        _add_run(profile_para, content.profile)

    if content.skill_groups:
        _add_section_heading(doc, "Skills")

        for group in content.skill_groups:
            _add_skill_group(doc, group)

    if content.experience:
        _add_section_heading(doc, "Experience")

        for entry in content.experience:
            _add_entry(doc, entry)

    if content.education:
        _add_section_heading(doc, "Education")

        for entry in content.education:
            _add_entry(doc, entry)

    if content.projects:
        _add_section_heading(doc, "Projects")

        for entry in content.projects:
            _add_entry(doc, entry)

    if content.certifications:
        _add_section_heading(doc, "Certifications")

        for cert in content.certifications:
            _add_certification(doc, cert)

    if content.languages:
        _add_section_heading(doc, "Languages")

        for language in content.languages:
            _add_language(doc, language)

    if content.coursework:
        _add_section_heading(doc, "Coursework")

        for item in content.coursework:
            _add_bullet(doc, item)

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    doc.save(str(out_path))

    return out_path
