from __future__ import annotations

import json
import re
from pathlib import Path

from PIL import Image
from docx import Document
from docx.enum.section import WD_SECTION_START
from docx.enum.table import WD_CELL_VERTICAL_ALIGNMENT, WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_TAB_ALIGNMENT, WD_TAB_LEADER
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor


ROOT = Path("/Users/mounir/Documents/Claude/Projects/DataWatch")
SOURCE = ROOT / "docs/pfe/report_source.json"
DATABASE_EVIDENCE = ROOT / "docs/pfe/database_evidence.json"
OUT = ROOT / "output/pfe/Rapport_PFE_DataWatch_Mounir_Gaiby.docx"
PAGE_MAP_PATH = ROOT / "tmp/pfe/report-page-map.json"

FONT = "Times New Roman"
INK = "202124"
MUTED = "5F6368"
LIGHT = "EEF0F3"
ACCENT = "B1202D"
ACCENT_SOFT = "F8EAEC"

FIGURE_CATALOG = [
    ("Figure 1.1", "Planification du PFE du 1er juin au 31 août et continuité du produit", "docs/diagrams/pfe/gantt-doc.png"),
    ("Figure 3.1", "Vue globale des acteurs et domaines fonctionnels", "docs/diagrams/pfe/use_cases-doc.png"),
    ("Figure 3.2", "Cas d’utilisation du workspace client", "docs/diagrams/pfe/use_cases_workspace-doc.png"),
    ("Figure 3.3", "Cas d’utilisation du portail staff", "docs/diagrams/pfe/use_cases_staff-doc.png"),
    ("Figure 3.4", "Séquence de connexion et d’inscription d’une source", "docs/diagrams/pfe/sequence_source-doc.png"),
    ("Figure 3.5", "Séquence de profilage et de détection", "docs/diagrams/pfe/sequence_monitoring-doc.png"),
    ("Figure 3.6", "Séquence d’investigation d’un incident", "docs/diagrams/pfe/sequence_investigation-doc.png"),
    ("Figure 3.7", "Séquence d’évaluation de la gouvernance IA", "docs/diagrams/pfe/sequence_ai_governance-doc.png"),
    ("Figure 3.8", "Cycle de vie d’un incident DataWatch", "docs/diagrams/pfe/activity_incident-doc.png"),
    ("Figure 3.9", "Classes du noyau de surveillance", "docs/diagrams/pfe/classes_monitoring-doc.png"),
    ("Figure 3.10", "Classes d’identité et de collaboration", "docs/diagrams/pfe/classes_collaboration-doc.png"),
    ("Figure 3.11", "Classes des moniteurs typés et révisions", "docs/diagrams/pfe/classes_monitors-doc.png"),
    ("Figure 3.12", "Classes du registre de gouvernance IA", "docs/diagrams/pfe/classes_ai_governance-doc.png"),
    ("Figure 3.13", "Architecture logique en couches", "docs/diagrams/pfe/architecture-doc.png"),
    ("Figure 3.14", "Déploiement de la pile de démonstration", "docs/diagrams/pfe/deployment-doc.png"),
    ("Figure 3.15", "Cartographie des 29 tables applicatives", "docs/diagrams/pfe/erd_overview-doc.png"),
    ("Figure 3.16", "Modèle relationnel du cœur de surveillance", "docs/diagrams/pfe/erd_core-doc.png"),
    ("Figure 3.17", "Modèle relationnel identité, équipes et astreintes", "docs/diagrams/pfe/erd_identity-doc.png"),
    ("Figure 3.18", "Modèle relationnel du registre de gouvernance IA", "docs/diagrams/pfe/erd_ai_governance-doc.png"),
    ("Figure 4.1", "Connexion au workspace Acme Corp", "docs/screenshots/pfe/01-workspace-login-report.png"),
    ("Figure 4.2", "Vue Opérations et incidents prioritaires", "docs/screenshots/pfe/02-operations-report.png"),
    ("Figure 4.3", "Catalogue des tables surveillées", "docs/screenshots/pfe/03-tables-catalogue-report.png"),
    ("Figure 4.4", "Liste filtrable des incidents", "docs/screenshots/pfe/04-incidents-list-report.png"),
    ("Figure 4.5", "Détail de l’incident critique orders", "docs/screenshots/pfe/05-incident-detail-report.png"),
    ("Figure 4.6", "Analyse IA de l’incident et actions proposées", "docs/screenshots/pfe/06-incident-ai-analysis-report.png"),
    ("Figure 4.7", "Profil de la table public.orders", "docs/screenshots/pfe/07-table-orders-report.png"),
    ("Figure 4.8", "Recommandations de moniteurs pour public.orders", "docs/screenshots/pfe/08-monitor-recommendations-report.png"),
    ("Figure 4.9", "Catalogue des moniteurs typés", "docs/screenshots/pfe/09-monitors-catalogue-report.png"),
    ("Figure 4.10", "Constructeur de moniteur DSL", "docs/screenshots/pfe/10-monitor-builder-report.png"),
    ("Figure 4.11", "Rapports hebdomadaires de santé", "docs/screenshots/pfe/11-weekly-reports-report.png"),
    ("Figure 4.12", "Répertoire des équipes", "docs/screenshots/pfe/12-teams-report.png"),
    ("Figure 4.13", "Membres de l’équipe Data Engineering", "docs/screenshots/pfe/13-team-detail-report.png"),
    ("Figure 4.14", "Sources de données enregistrées", "docs/screenshots/pfe/14-data-sources-report.png"),
    ("Figure 4.15", "Catalogue des connecteurs disponibles", "docs/screenshots/pfe/15-connector-catalogue-report.png"),
    ("Figure 4.16", "Routes d’alerte par canal et sévérité", "docs/screenshots/pfe/16-alert-routes-report.png"),
    ("Figure 4.17", "Préférences individuelles de notification", "docs/screenshots/pfe/17-notification-preferences-report.png"),
    ("Figure 4.18", "File de travail de gouvernance IA", "docs/screenshots/pfe/18-ai-systems-report.png"),
    ("Figure 4.19", "Détail d’un système IA déclaré", "docs/screenshots/pfe/19-ai-governance-detail-report.png"),
    ("Figure 4.20", "Chronologie des preuves de gouvernance", "docs/screenshots/pfe/20-ai-evidence-timeline-report.png"),
    ("Figure 4.21", "Connexion isolée au portail staff", "docs/screenshots/pfe/21-staff-login-report.png"),
    ("Figure 4.22", "Administration des organisations clientes", "docs/screenshots/pfe/22-admin-organizations-report.png"),
    ("Figure 4.23", "Tableau de bord global du portail staff", "docs/screenshots/pfe/23-admin-dashboard-report.png"),
    ("Figure 4.24", "Détail opérationnel de l’organisation Acme Corp", "docs/screenshots/pfe/24-admin-organization-detail-report.png"),
]
FIGURES = {label: ROOT / path for label, _, path in FIGURE_CATALOG}
FIGURE_META = {label: (caption, ROOT / path) for label, caption, path in FIGURE_CATALOG}
SAMPLE_TABLES = [
    ("organizations", "Organisations de démonstration"),
    ("acme_users", "Utilisateurs Acme sans identifiants sensibles"),
    ("acme_teams", "Équipes Acme"),
    ("acme_sources", "Sources Acme"),
    ("acme_tables", "Tables surveillées chez Acme"),
    ("acme_incidents", "Incidents Acme ouverts"),
    ("acme_ai_systems", "Systèmes IA déclarés"),
]

SKIP_BODY_INDEXES = (
    set(range(185, 190)) | set(range(199, 204)) | set(range(241, 246)) |
    {152, 190, 193, 196, 204, 223, 224, 227, 228, 231, 232, 235, 236, 237, 238, 246, 253}
)


def set_font(run, size=None, bold=None, italic=None, color=None):
    run.font.name = FONT
    run._element.get_or_add_rPr().get_or_add_rFonts().set(qn("w:ascii"), FONT)
    run._element.get_or_add_rPr().get_or_add_rFonts().set(qn("w:hAnsi"), FONT)
    if size is not None:
        run.font.size = Pt(size)
    if bold is not None:
        run.bold = bold
    if italic is not None:
        run.italic = italic
    if color is not None:
        run.font.color.rgb = RGBColor.from_string(color)


def paragraph_border(paragraph, color=ACCENT, size="14", space="6"):
    p_pr = paragraph._p.get_or_add_pPr()
    p_bdr = p_pr.find(qn("w:pBdr"))
    if p_bdr is None:
        p_bdr = OxmlElement("w:pBdr")
        p_pr.append(p_bdr)
    bottom = OxmlElement("w:bottom")
    bottom.set(qn("w:val"), "single")
    bottom.set(qn("w:sz"), size)
    bottom.set(qn("w:space"), space)
    bottom.set(qn("w:color"), color)
    p_bdr.append(bottom)


def remove_paragraph_border(paragraph):
    p_pr = paragraph._p.get_or_add_pPr()
    p_bdr = p_pr.find(qn("w:pBdr"))
    if p_bdr is not None:
        p_pr.remove(p_bdr)


def add_field(paragraph, instruction, fallback=""):
    begin = OxmlElement("w:fldChar")
    begin.set(qn("w:fldCharType"), "begin")
    instr = OxmlElement("w:instrText")
    instr.set(qn("xml:space"), "preserve")
    instr.text = instruction
    separate = OxmlElement("w:fldChar")
    separate.set(qn("w:fldCharType"), "separate")
    end = OxmlElement("w:fldChar")
    end.set(qn("w:fldCharType"), "end")
    r1 = OxmlElement("w:r"); r1.append(begin)
    r2 = OxmlElement("w:r"); r2.append(instr)
    r3 = OxmlElement("w:r"); r3.append(separate)
    paragraph._p.extend([r1, r2, r3])
    if fallback:
        run = paragraph.add_run(fallback)
        set_font(run, 10, color=MUTED)
    r4 = OxmlElement("w:r"); r4.append(end)
    paragraph._p.append(r4)


def set_page_numbering(section, fmt, start=1):
    sect_pr = section._sectPr
    pg = sect_pr.find(qn("w:pgNumType"))
    if pg is None:
        pg = OxmlElement("w:pgNumType")
        sect_pr.append(pg)
    pg.set(qn("w:fmt"), fmt)
    pg.set(qn("w:start"), str(start))


def clear_container(container):
    for p in list(container.paragraphs):
        if p._p.getparent() is not None:
            p._p.getparent().remove(p._p)


def set_footer(section, numbered=True):
    section.footer.is_linked_to_previous = False
    clear_container(section.footer)
    p = section.footer.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.space_before = Pt(2)
    p.paragraph_format.space_after = Pt(0)
    if numbered:
        run = p.add_run("—  ")
        set_font(run, 8.5, color=MUTED)
        add_field(p, "PAGE")
        run = p.add_run("  —")
        set_font(run, 8.5, color=MUTED)


def set_header(section, text=""):
    section.header.is_linked_to_previous = False
    clear_container(section.header)
    p = section.header.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    p.paragraph_format.space_after = Pt(0)
    if text:
        run = p.add_run(text)
        set_font(run, 8, color=MUTED)


def section_geometry(section):
    section.page_width = Cm(21.0)
    section.page_height = Cm(29.7)
    section.left_margin = Cm(3.0)
    section.right_margin = Cm(2.2)
    section.top_margin = Cm(2.2)
    section.bottom_margin = Cm(2.2)
    section.header_distance = Cm(0.9)
    section.footer_distance = Cm(1.0)


def update_fields_on_open(doc):
    settings = doc.settings._element
    node = settings.find(qn("w:updateFields"))
    if node is None:
        node = OxmlElement("w:updateFields")
        settings.append(node)
    node.set(qn("w:val"), "true")


def configure_styles(doc):
    styles = doc.styles
    normal = styles["Normal"]
    normal.font.name = FONT
    normal._element.rPr.rFonts.set(qn("w:ascii"), FONT)
    normal._element.rPr.rFonts.set(qn("w:hAnsi"), FONT)
    normal.font.size = Pt(12)
    normal.font.color.rgb = RGBColor.from_string(INK)
    normal.paragraph_format.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    normal.paragraph_format.space_before = Pt(0)
    normal.paragraph_format.space_after = Pt(7)
    normal.paragraph_format.line_spacing = 1.35
    normal.paragraph_format.widow_control = True

    h1 = styles["Heading 1"]
    h1.font.name = FONT; h1.font.size = Pt(19); h1.font.bold = True; h1.font.color.rgb = RGBColor.from_string(INK)
    h1._element.rPr.rFonts.set(qn("w:ascii"), FONT); h1._element.rPr.rFonts.set(qn("w:hAnsi"), FONT)
    h1.paragraph_format.space_before = Pt(6); h1.paragraph_format.space_after = Pt(14)
    h1.paragraph_format.keep_with_next = True; h1.paragraph_format.page_break_before = True

    h2 = styles["Heading 2"]
    h2.font.name = FONT; h2.font.size = Pt(14.5); h2.font.bold = True; h2.font.color.rgb = RGBColor.from_string(INK)
    h2._element.rPr.rFonts.set(qn("w:ascii"), FONT); h2._element.rPr.rFonts.set(qn("w:hAnsi"), FONT)
    h2.paragraph_format.space_before = Pt(14); h2.paragraph_format.space_after = Pt(6)
    h2.paragraph_format.keep_with_next = True

    h3 = styles["Heading 3"]
    h3.font.name = FONT; h3.font.size = Pt(12.5); h3.font.bold = True; h3.font.color.rgb = RGBColor.from_string(INK)
    h3._element.rPr.rFonts.set(qn("w:ascii"), FONT); h3._element.rPr.rFonts.set(qn("w:hAnsi"), FONT)
    h3.paragraph_format.space_before = Pt(10); h3.paragraph_format.space_after = Pt(4)
    h3.paragraph_format.keep_with_next = True

    cap = styles["Caption"]
    cap.font.name = FONT; cap.font.size = Pt(9); cap.font.italic = False; cap.font.color.rgb = RGBColor.from_string(MUTED)
    cap._element.rPr.rFonts.set(qn("w:ascii"), FONT); cap._element.rPr.rFonts.set(qn("w:hAnsi"), FONT)
    cap.paragraph_format.alignment = WD_ALIGN_PARAGRAPH.CENTER
    cap.paragraph_format.space_before = Pt(4); cap.paragraph_format.space_after = Pt(12)
    cap.paragraph_format.keep_with_next = False; cap.paragraph_format.keep_together = True


def add_numbering(doc):
    root = doc.part.numbering_part.element
    existing_abs = [int(x.get(qn("w:abstractNumId"))) for x in root.findall(qn("w:abstractNum"))]
    existing_num = [int(x.get(qn("w:numId"))) for x in root.findall(qn("w:num"))]
    next_abs = max(existing_abs or [0]) + 1
    next_num = max(existing_num or [0]) + 1

    def create(abstract_id, num_id, fmt, text):
        abstract = OxmlElement("w:abstractNum"); abstract.set(qn("w:abstractNumId"), str(abstract_id))
        multi = OxmlElement("w:multiLevelType"); multi.set(qn("w:val"), "singleLevel"); abstract.append(multi)
        lvl = OxmlElement("w:lvl"); lvl.set(qn("w:ilvl"), "0"); abstract.append(lvl)
        start = OxmlElement("w:start"); start.set(qn("w:val"), "1"); lvl.append(start)
        nf = OxmlElement("w:numFmt"); nf.set(qn("w:val"), fmt); lvl.append(nf)
        lt = OxmlElement("w:lvlText"); lt.set(qn("w:val"), text); lvl.append(lt)
        jc = OxmlElement("w:lvlJc"); jc.set(qn("w:val"), "left"); lvl.append(jc)
        ppr = OxmlElement("w:pPr")
        tabs = OxmlElement("w:tabs"); tab = OxmlElement("w:tab"); tab.set(qn("w:val"), "num"); tab.set(qn("w:pos"), "720"); tabs.append(tab); ppr.append(tabs)
        ind = OxmlElement("w:ind"); ind.set(qn("w:left"), "720"); ind.set(qn("w:hanging"), "360"); ppr.append(ind); lvl.append(ppr)
        rpr = OxmlElement("w:rPr"); fonts = OxmlElement("w:rFonts"); fonts.set(qn("w:ascii"), FONT); fonts.set(qn("w:hAnsi"), FONT); rpr.append(fonts); lvl.append(rpr)
        root.insert(0, abstract)
        num = OxmlElement("w:num"); num.set(qn("w:numId"), str(num_id)); aid = OxmlElement("w:abstractNumId"); aid.set(qn("w:val"), str(abstract_id)); num.append(aid); root.append(num)

    create(next_abs, next_num, "bullet", "•")
    create(next_abs + 1, next_num + 1, "decimal", "%1.")
    return next_num, next_num + 1


def set_num(paragraph, num_id):
    ppr = paragraph._p.get_or_add_pPr()
    num_pr = OxmlElement("w:numPr")
    ilvl = OxmlElement("w:ilvl"); ilvl.set(qn("w:val"), "0")
    nid = OxmlElement("w:numId"); nid.set(qn("w:val"), str(num_id))
    num_pr.extend([ilvl, nid]); ppr.append(num_pr)


def add_body(doc, text, *, align=WD_ALIGN_PARAGRAPH.JUSTIFY, italic=False, bold=False, after=7):
    p = doc.add_paragraph(style="Normal")
    p.alignment = align
    p.paragraph_format.space_after = Pt(after)
    run = p.add_run(text)
    set_font(run, 12, bold=bold, italic=italic, color=INK)
    return p


def add_list(doc, text, num_id):
    p = doc.add_paragraph(style="Normal")
    set_num(p, num_id)
    p.alignment = WD_ALIGN_PARAGRAPH.LEFT
    p.paragraph_format.space_after = Pt(4)
    p.paragraph_format.line_spacing = 1.2
    run = p.add_run(text)
    set_font(run, 11.5, color=INK)
    return p


def add_callout(doc, title, text):
    table = doc.add_table(rows=1, cols=1)
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    # Word exposes the shaded callout as a one-row table to assistive tools.
    # Mark that semantic row explicitly so the label is announced as its header.
    tr_pr = table.rows[0]._tr.get_or_add_trPr()
    tbl_header = OxmlElement("w:tblHeader")
    tbl_header.set(qn("w:val"), "true")
    tr_pr.append(tbl_header)
    cell = table.cell(0, 0)
    set_table_cell_margins(cell, top=150, start=220, bottom=150, end=220)
    shd = OxmlElement("w:shd"); shd.set(qn("w:fill"), "F7F7F8"); cell._tc.get_or_add_tcPr().append(shd)
    borders = OxmlElement("w:tcBorders")
    start = OxmlElement("w:start"); start.set(qn("w:val"), "single"); start.set(qn("w:sz"), "18"); start.set(qn("w:color"), ACCENT); borders.append(start)
    for edge in ("top", "bottom", "end"):
        node = OxmlElement("w:" + edge); node.set(qn("w:val"), "nil"); borders.append(node)
    cell._tc.get_or_add_tcPr().append(borders)
    p = cell.paragraphs[0]; p.paragraph_format.space_after = Pt(3)
    r = p.add_run(title.upper()); set_font(r, 9, bold=True, color=ACCENT)
    p = cell.add_paragraph(); p.paragraph_format.space_after = Pt(0); p.paragraph_format.line_spacing = 1.2
    r = p.add_run(text); set_font(r, 10.5, color=INK)
    spacer = doc.add_paragraph(); spacer.paragraph_format.space_after = Pt(2)
    return table


def add_academic_table(doc, label, caption, headers, rows, widths, anchor, bookmark_id):
    cap = doc.add_paragraph(style="Caption")
    cap.alignment = WD_ALIGN_PARAGRAPH.LEFT
    cap.paragraph_format.space_before = Pt(8); cap.paragraph_format.space_after = Pt(5); cap.paragraph_format.keep_with_next = True
    r = cap.add_run(label); set_font(r, 9.5, bold=True, color=ACCENT)
    r = cap.add_run(" — " + caption); set_font(r, 9.5, color=MUTED)
    add_bookmark(cap, anchor, bookmark_id)
    table = doc.add_table(rows=1, cols=len(headers))
    table.alignment = WD_TABLE_ALIGNMENT.CENTER; table.autofit = False
    grid = table._tbl.tblGrid
    for child in list(grid): grid.remove(child)
    for width in widths:
        col = OxmlElement("w:gridCol"); col.set(qn("w:w"), str(width)); grid.append(col)
    for i, text in enumerate(headers):
        cell = table.rows[0].cells[i]; set_cell_width(cell, widths[i]); set_table_cell_margins(cell, 120, 140, 120, 140)
        cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
        shd = OxmlElement("w:shd"); shd.set(qn("w:fill"), ACCENT); cell._tc.get_or_add_tcPr().append(shd)
        cell.text = ""; p = cell.paragraphs[0]; p.alignment = WD_ALIGN_PARAGRAPH.LEFT; p.paragraph_format.space_after = Pt(0)
        r = p.add_run(text); set_font(r, 9.2, bold=True, color="FFFFFF")
    tr_pr = table.rows[0]._tr.get_or_add_trPr(); header = OxmlElement("w:tblHeader"); header.set(qn("w:val"), "true"); tr_pr.append(header)
    for row_idx, values in enumerate(rows):
        cells = table.add_row().cells
        for i, value in enumerate(values):
            cell = cells[i]; set_cell_width(cell, widths[i]); set_table_cell_margins(cell, 115, 140, 115, 140)
            cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
            if row_idx % 2:
                shd = OxmlElement("w:shd"); shd.set(qn("w:fill"), "F7F7F8"); cell._tc.get_or_add_tcPr().append(shd)
            cell.text = ""; p = cell.paragraphs[0]; p.paragraph_format.space_after = Pt(0); p.paragraph_format.line_spacing = 1.1
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER if i == 0 and len(value) < 18 else WD_ALIGN_PARAGRAPH.LEFT
            r = p.add_run(value); set_font(r, 9.2, bold=(i == 0), color=INK)
    for row in table.rows:
        for cell in row.cells:
            tc_pr = cell._tc.get_or_add_tcPr(); borders = OxmlElement("w:tcBorders")
            for edge in ("top", "bottom"):
                node = OxmlElement("w:" + edge); node.set(qn("w:val"), "single"); node.set(qn("w:sz"), "3"); node.set(qn("w:color"), "D7DADF"); borders.append(node)
            for edge in ("start", "end"):
                node = OxmlElement("w:" + edge); node.set(qn("w:val"), "nil"); borders.append(node)
            tc_pr.append(borders)
    p = doc.add_paragraph(); p.paragraph_format.space_after = Pt(5)
    r = p.add_run("Source : élaboration personnelle à partir de la conception et des validations de DataWatch.")
    set_font(r, 8.5, italic=True, color=MUTED)
    return bookmark_id + 1


def add_bookmark(paragraph, name, bookmark_id):
    start = OxmlElement("w:bookmarkStart"); start.set(qn("w:id"), str(bookmark_id)); start.set(qn("w:name"), name)
    end = OxmlElement("w:bookmarkEnd"); end.set(qn("w:id"), str(bookmark_id))
    paragraph._p.insert(1, start); paragraph._p.append(end)


def add_internal_link(paragraph, text, anchor, bold=False):
    hyperlink = OxmlElement("w:hyperlink"); hyperlink.set(qn("w:anchor"), anchor); hyperlink.set(qn("w:history"), "1")
    run = OxmlElement("w:r"); rpr = OxmlElement("w:rPr")
    rstyle = OxmlElement("w:rStyle"); rstyle.set(qn("w:val"), "Hyperlink"); rpr.append(rstyle)
    fonts = OxmlElement("w:rFonts"); fonts.set(qn("w:ascii"), FONT); fonts.set(qn("w:hAnsi"), FONT); rpr.append(fonts)
    size = OxmlElement("w:sz"); size.set(qn("w:val"), "17"); rpr.append(size)
    color = OxmlElement("w:color"); color.set(qn("w:val"), INK); rpr.append(color)
    if bold: rpr.append(OxmlElement("w:b"))
    run.append(rpr); node = OxmlElement("w:t"); node.text = text; run.append(node); hyperlink.append(run); paragraph._p.append(hyperlink)


def add_heading(doc, text, level, front=False, anchor=None, bookmark_id=None):
    p = doc.add_paragraph(style=f"Heading {level}")
    if level == 1:
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER if front else WD_ALIGN_PARAGRAPH.LEFT
        if front:
            p.paragraph_format.space_after = Pt(20)
            remove_paragraph_border(p)
        else:
            paragraph_border(p)
    run = p.add_run(text)
    set_font(run, 19 if level == 1 else (14.5 if level == 2 else 12.5), bold=True, color=INK)
    if anchor is not None:
        add_bookmark(p, anchor, bookmark_id)
    return p


def add_live_index(doc, entries, instruction):
    """Add a Word-updatable index with visible, clickable cached results."""
    sdt = OxmlElement("w:sdt")
    sdt_pr = OxmlElement("w:sdtPr")
    doc_part = OxmlElement("w:docPartObj")
    gallery = OxmlElement("w:docPartGallery"); gallery.set(qn("w:val"), "Table of Contents")
    unique = OxmlElement("w:docPartUnique")
    doc_part.extend([gallery, unique]); sdt_pr.append(doc_part); sdt.append(sdt_pr)
    content = OxmlElement("w:sdtContent")
    made = []
    for text, page, anchor, level in entries:
        p = doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.LEFT
        p.paragraph_format.left_indent = Cm(1.0 if level == 3 else (0.5 if level == 2 else 0))
        p.paragraph_format.space_before = Pt(0); p.paragraph_format.space_after = Pt(1.2); p.paragraph_format.line_spacing = 1.0
        p.paragraph_format.tab_stops.add_tab_stop(Cm(15.2), WD_TAB_ALIGNMENT.RIGHT, WD_TAB_LEADER.DOTS)
        if anchor is None:
            r = p.add_run(text.upper()); set_font(r, 9, bold=True, color=ACCENT)
        else:
            add_internal_link(p, text, anchor, bold=(level == 1))
            r = p.add_run("\t" + str(page)); set_font(r, 8.7, bold=(level == 1), color=INK)
        made.append(p)
    first = made[0]._p
    begin = OxmlElement("w:r"); char = OxmlElement("w:fldChar"); char.set(qn("w:fldCharType"), "begin"); begin.append(char)
    instr_r = OxmlElement("w:r"); instr = OxmlElement("w:instrText"); instr.set(qn("xml:space"), "preserve"); instr.text = instruction; instr_r.append(instr)
    sep_r = OxmlElement("w:r"); sep = OxmlElement("w:fldChar"); sep.set(qn("w:fldCharType"), "separate"); sep_r.append(sep)
    first.insert(1, begin); first.insert(2, instr_r); first.insert(3, sep_r)
    end_r = OxmlElement("w:r"); end = OxmlElement("w:fldChar"); end.set(qn("w:fldCharType"), "end"); end_r.append(end); made[-1]._p.append(end_r)
    for p in made:
        p._p.getparent().remove(p._p); content.append(p._p)
    sdt.append(content)
    body = doc._body._body
    body.insert(body.index(body.sectPr), sdt)


def add_static_index(doc, entries):
    """Add a deterministic, clickable list of figures or tables."""
    for text, page, anchor, level in entries:
        p = doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.LEFT
        p.paragraph_format.space_before = Pt(4 if anchor is None else 0)
        p.paragraph_format.space_after = Pt(4 if anchor is None else 5)
        p.paragraph_format.left_indent = Cm(0.5 if anchor else 0)
        if anchor is None:
            r = p.add_run(text.upper()); set_font(r, 10.5, bold=True, color=ACCENT)
            continue
        p.paragraph_format.tab_stops.add_tab_stop(Cm(15.2), WD_TAB_ALIGNMENT.RIGHT, WD_TAB_LEADER.DOTS)
        add_internal_link(p, text, anchor, bold=False)
        r = p.add_run("\t" + str(page)); set_font(r, 10, color=INK)


def add_picture(doc, path, label, caption, anchor=None, bookmark_id=None):
    if not path.exists():
        raise FileNotFoundError(path)
    with Image.open(path) as im:
        w, h = im.size
    max_w = 15.8
    max_h = 15.2
    width = max_w
    height = width * h / w
    if height > max_h:
        height = max_h
        width = height * w / h
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.space_before = Pt(8)
    p.paragraph_format.space_after = Pt(0)
    p.paragraph_format.keep_with_next = True
    run = p.add_run()
    shape = run.add_picture(str(path), width=Cm(width), height=Cm(height))
    doc_pr = shape._inline.docPr
    doc_pr.set("descr", caption)
    cap = doc.add_paragraph(style="Caption")
    r = cap.add_run(label)
    set_font(r, 9, bold=True, color=ACCENT)
    r = cap.add_run(" — " + caption)
    set_font(r, 9, color=MUTED)
    if anchor is not None:
        add_bookmark(cap, anchor, bookmark_id)


def add_code_block(doc, lines):
    for line in lines:
        p = doc.add_paragraph()
        p.paragraph_format.left_indent = Cm(0.5)
        p.paragraph_format.right_indent = Cm(0.5)
        p.paragraph_format.space_before = Pt(0)
        p.paragraph_format.space_after = Pt(0)
        p.alignment = WD_ALIGN_PARAGRAPH.LEFT
        ppr = p._p.get_or_add_pPr(); shd = OxmlElement("w:shd"); shd.set(qn("w:fill"), "F3F4F6"); ppr.append(shd)
        run = p.add_run(line)
        set_font(run, 9, color=INK)
        run.font.name = "Courier New"
        run._element.rPr.rFonts.set(qn("w:ascii"), "Courier New"); run._element.rPr.rFonts.set(qn("w:hAnsi"), "Courier New")


def set_table_cell_margins(cell, top=100, start=140, bottom=100, end=140):
    tc = cell._tc; tc_pr = tc.get_or_add_tcPr()
    tc_mar = tc_pr.first_child_found_in("w:tcMar")
    if tc_mar is None:
        tc_mar = OxmlElement("w:tcMar"); tc_pr.append(tc_mar)
    for tag, val in (("top", top), ("start", start), ("bottom", bottom), ("end", end)):
        node = tc_mar.find(qn("w:" + tag))
        if node is None:
            node = OxmlElement("w:" + tag); tc_mar.append(node)
        node.set(qn("w:w"), str(val)); node.set(qn("w:type"), "dxa")


def set_cell_width(cell, dxa):
    tc_pr = cell._tc.get_or_add_tcPr(); tc_w = tc_pr.find(qn("w:tcW"))
    if tc_w is None:
        tc_w = OxmlElement("w:tcW"); tc_pr.append(tc_w)
    tc_w.set(qn("w:w"), str(dxa)); tc_w.set(qn("w:type"), "dxa")


def add_abbreviations(doc):
    rows = [
        ("API", "Application Programming Interface"), ("IA", "Intelligence artificielle"),
        ("LLM", "Large Language Model"), ("SaaS", "Software as a Service"),
        ("SLA", "Service Level Agreement"), ("JWT", "JSON Web Token"),
        ("ORM", "Object Relational Mapping"), ("CI", "Continuous Integration"),
    ]
    table = doc.add_table(rows=1, cols=2)
    table.alignment = WD_TABLE_ALIGNMENT.CENTER; table.autofit = False
    tbl_pr = table._tbl.tblPr
    tbl_w = tbl_pr.find(qn("w:tblW")); tbl_w.set(qn("w:type"), "dxa"); tbl_w.set(qn("w:w"), "8950")
    grid = table._tbl.tblGrid
    for child in list(grid): grid.remove(child)
    for width in (2200, 6750):
        col = OxmlElement("w:gridCol"); col.set(qn("w:w"), str(width)); grid.append(col)
    for i, text in enumerate(("Abréviation", "Signification")):
        c = table.rows[0].cells[i]; set_cell_width(c, (2200, 6750)[i]); set_table_cell_margins(c)
        c.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
        shd = OxmlElement("w:shd"); shd.set(qn("w:fill"), ACCENT_SOFT); c._tc.get_or_add_tcPr().append(shd)
        c.text = ""; p = c.paragraphs[0]; p.alignment = WD_ALIGN_PARAGRAPH.LEFT
        r = p.add_run(text); set_font(r, 10, bold=True, color=INK)
    tr_pr = table.rows[0]._tr.get_or_add_trPr()
    header = OxmlElement("w:tblHeader"); header.set(qn("w:val"), "true"); tr_pr.append(header)
    for abbr, meaning in rows:
        cells = table.add_row().cells
        for i, text in enumerate((abbr, meaning)):
            set_cell_width(cells[i], (2200, 6750)[i]); set_table_cell_margins(cells[i]); cells[i].vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
            cells[i].text = ""; p = cells[i].paragraphs[0]; p.paragraph_format.space_after = Pt(0)
            r = p.add_run(text); set_font(r, 10, bold=(i == 0), color=INK)
    # Quiet horizontal rules only.
    for row in table.rows:
        for cell in row.cells:
            tc_pr = cell._tc.get_or_add_tcPr(); borders = OxmlElement("w:tcBorders")
            for edge in ("top", "bottom"):
                e = OxmlElement("w:" + edge); e.set(qn("w:val"), "single"); e.set(qn("w:sz"), "4"); e.set(qn("w:color"), "D7DADF"); borders.append(e)
            for edge in ("start", "end"):
                e = OxmlElement("w:" + edge); e.set(qn("w:val"), "nil"); borders.append(e)
            tc_pr.append(borders)


def remap_heading(text):
    replacements = {
        "1. Introduction générale": "INTRODUCTION GÉNÉRALE",
        "1.1 Résultats attendus": "1.3 Résultats attendus",
        "1.2 Organisation du rapport": "1.4 Organisation du rapport",
        "2.3.1 Problématique": "1.3.4 Problématique",
        "2.3.2 Solution proposée": "1.3.5 Solution proposée",
        "4.3.1 Diagramme de séquence": "3.3.2 Diagramme de séquence",
        "4.3.2 Diagramme de classes": "3.3.3 Diagramme de classes",
        "6. Conclusion générale et perspectives": "CONCLUSION GÉNÉRALE ET PERSPECTIVES",
        "6.1 Cadre du travail": "Cadre du travail",
        "6.2 Synthèse des apports": "Synthèse des apports",
        "6.3 Perspectives": "Perspectives",
        "7. Références": "RÉFÉRENCES",
        "8. Annexes": "ANNEXES",
    }
    if text in replacements:
        return replacements[text]
    m = re.match(r"([2-5])\. Chapitre ([1-4]) : (.+)", text)
    if m:
        return f"CHAPITRE {m.group(2)} — {m.group(3).upper()}"
    m = re.match(r"([2-5])\.(\d(?:\.\d)?) (.+)", text)
    if m:
        old = int(m.group(1)); return f"{old-1}.{m.group(2)} {m.group(3)}"
    return text


def heading_anchor(text):
    value = re.sub(r"[^A-Za-z0-9]+", "_", text).strip("_")
    return ("extra_" + value)[:38]


def cover(doc):
    p = doc.add_paragraph(); p.alignment = WD_ALIGN_PARAGRAPH.CENTER; p.paragraph_format.space_after = Pt(12)
    logo = p.add_run().add_picture(str(ROOT / "docs/pfe/assets/isga-logo.png"), width=Cm(5.8))
    logo._inline.docPr.set("descr", "Logo officiel de l’ISGA")
    p = doc.add_paragraph(); p.alignment = WD_ALIGN_PARAGRAPH.CENTER; p.paragraph_format.space_after = Pt(2)
    r = p.add_run("ISGA CASABLANCA"); set_font(r, 11, bold=True, color=INK)
    p = doc.add_paragraph(); p.alignment = WD_ALIGN_PARAGRAPH.CENTER; p.paragraph_format.space_after = Pt(16)
    r = p.add_run("3CI — Big Data et Intelligence Artificielle"); set_font(r, 10, color=MUTED)
    p = doc.add_paragraph(); p.alignment = WD_ALIGN_PARAGRAPH.CENTER; p.paragraph_format.space_before = Pt(6); p.paragraph_format.space_after = Pt(22)
    r = p.add_run("PROJET DE FIN D’ÉTUDES"); set_font(r, 13, bold=True, color=ACCENT)
    paragraph_border(p, color=ACCENT, size="10", space="10")
    p = doc.add_paragraph(); p.alignment = WD_ALIGN_PARAGRAPH.CENTER; p.paragraph_format.space_before = Pt(16); p.paragraph_format.space_after = Pt(8)
    r = p.add_run("Conception et réalisation de DataWatch"); set_font(r, 24, bold=True, color=INK)
    p = doc.add_paragraph(); p.alignment = WD_ALIGN_PARAGRAPH.CENTER; p.paragraph_format.left_indent = Cm(1.0); p.paragraph_format.right_indent = Cm(1.0); p.paragraph_format.space_after = Pt(34)
    r = p.add_run("Plateforme SaaS multi-tenant de surveillance de la qualité des données, enrichie par l’IA pour l’explication des incidents"); set_font(r, 12.5, color=MUTED)
    entries = [("RÉALISÉ PAR", "Mounir Gaiby"), ("ENCADRÉ PAR", "Dr. HANINE MOHAMED"), ("FILIÈRE", "3CI — Big Data et Intelligence Artificielle")]
    for label, value in entries:
        p = doc.add_paragraph(); p.alignment = WD_ALIGN_PARAGRAPH.LEFT; p.paragraph_format.left_indent = Cm(0.25); p.paragraph_format.space_after = Pt(8)
        p.paragraph_format.tab_stops.add_tab_stop(Cm(6.2), WD_TAB_ALIGNMENT.LEFT)
        r = p.add_run(label); set_font(r, 8.5, bold=True, color=ACCENT)
        r = p.add_run("\t" + value); set_font(r, 10.5, bold=True, color=INK)
    p = doc.add_paragraph(); p.alignment = WD_ALIGN_PARAGRAPH.CENTER; p.paragraph_format.space_before = Pt(30)
    r = p.add_run("Année universitaire 2025–2026"); set_font(r, 10, color=MUTED)


def is_bullet_index(index):
    return index in set(range(122, 127)) | set(range(177, 183)) | set(range(264, 270))


ENRICHMENTS = {
    "1. Introduction générale": [
        ("h2", "1.1 Contexte et motivation"),
        ("p", "La transformation numérique a placé la donnée au centre des processus de pilotage, de recommandation et d’automatisation. Une rupture de fraîcheur, une dérive de schéma ou une augmentation silencieuse des valeurs manquantes peut donc contaminer plusieurs usages avant d’être visible. Les équipes doivent surveiller des actifs distribués entre bases transactionnelles, entrepôts analytiques et services cloud, tout en conservant assez de contexte pour distinguer un incident réel d’une variation normale."),
        ("p", "La qualité des données ne se réduit pas à la validité syntaxique. Elle englobe notamment l’exactitude, la complétude, la cohérence, l’actualité et la traçabilité. Le modèle ISO/IEC 25012 fournit un vocabulaire utile pour exprimer ces dimensions [9]. Dans ce projet, elles sont traduites en signaux observables : volume, fraîcheur, empreinte de schéma, taux de valeurs nulles, cardinalité et distributions numériques."),
        ("h2", "1.2 Problématique et démarche"),
        ("p", "La problématique retenue est la suivante : comment concevoir une plateforme SaaS capable de détecter précocement des anomalies de qualité, de les transformer en incidents compréhensibles et de guider l’investigation, sans exposer les données entre organisations ni présenter les sorties d’un modèle génératif comme des vérités opérationnelles ? Cette question combine des enjeux de génie logiciel, d’ingénierie des données, de sécurité et d’intelligence artificielle."),
        ("p", "La démarche suivie associe étude de l’existant, spécification des besoins, conception UML, architecture en couches, réalisation incrémentale et validation par preuves. Les décisions importantes sont reliées à des artefacts vérifiables : migrations, contrats d’API, tests, captures d’écran et jeux de démonstration. Cette discipline permet de présenter honnêtement ce qui fonctionne, ce qui reste expérimental et ce qui exigerait une validation supplémentaire avant une mise en production."),
        ("callout", "Question directrice", "Comment passer d’une métrique technique isolée à une décision d’exploitation traçable, tout en maintenant l’isolation multi-tenant et une frontière explicite entre fait observé, hypothèse IA et action humaine ?"),
    ],
    "2.2 Présentation de l’organisme d’accueil": [
        ("h3", "1.2.1 Présentation de l’ISGA"),
        ("p", "L’ISGA est un établissement marocain d’enseignement supérieur qui forme des ingénieurs et des managers. Son cycle d’ingénieur s’inscrit dans un cursus de cinq années et met l’accent sur la maîtrise scientifique, la conduite de projets complexes, l’ouverture professionnelle et la capacité d’adaptation [10]. Le campus de Casablanca accueille notamment la spécialisation Intelligence Artificielle et Big Data, qui fournit le cadre académique de ce projet."),
        ("h3", "1.2.2 Environnement pédagogique du projet"),
        ("p", "Le projet a été réalisé dans le cadre du Projet de Fin d’Études de la troisième année du cycle ingénieur. L’encadrement assure la cohérence méthodologique, la validation de la problématique et le suivi des livrables. Le travail couvre le cadrage, la conception, l’implémentation, les tests, la préparation d’une démonstration et la rédaction scientifique. Il ne correspond pas à une mission réalisée pour un client externe ; l’organisme d’accueil désigne ici l’environnement académique qui porte et évalue le projet."),
        ("table", "Tableau 1.1", "Acteurs et responsabilités du projet", ["Acteur", "Responsabilité principale", "Livrables associés"], [
            ["Étudiant", "Analyse, conception, développement, tests et documentation", "Code source, démonstration, rapport et présentation"],
            ["Encadrant", "Orientation scientifique et validation méthodologique", "Revues, recommandations et validation du périmètre"],
            ["Jury", "Évaluation de la pertinence, de la réalisation et de la maîtrise", "Questions, appréciation et décision académique"],
            ["Utilisateur cible", "Expression des besoins d’exploitation et d’investigation", "Scénarios d’usage et critères d’acceptation"],
        ], [1700, 3900, 3350], "tab_1_1"),
    ],
    "2.3 Présentation du projet": [
        ("h3", "1.3.1 Contexte métier"),
        ("p", "Les équipes data exploitent des tableaux de bord, des modèles analytiques et des services alimentés par des bases hétérogènes. Lorsqu’un jeu de données devient vide, obsolète ou incohérent, l’impact se propage aux décisions métiers. Les contrôles artisanaux détectent parfois l’écart, mais ils fournissent rarement une chronologie, un niveau de sévérité, un propriétaire et une procédure de résolution. DataWatch vise à réunir ces éléments dans un même parcours."),
        ("h3", "1.3.2 Périmètre fonctionnel"),
        ("p", "Le périmètre couvre l’authentification par organisation, le registre des sources, la découverte des schémas, la sélection des tables, le profilage périodique, la détection hybride, la gestion du cycle de vie des incidents, les alertes et la narration IA. Il inclut également des moniteurs typés et un plan de contrôle de gouvernance IA en mode d’observation. La facturation réelle, les garanties de disponibilité et l’exploitation à grande échelle sont hors du périmètre de preuve du PFE."),
        ("h3", "1.3.3 Utilisateurs cibles"),
        ("p", "La solution cible d’abord le data engineer chargé de fiabiliser les flux, l’analytics engineer responsable des modèles et indicateurs, et le responsable data qui souhaite une vision synthétique du risque. L’administrateur de l’organisation configure les accès et les routes d’alerte. Une séparation complémentaire réserve le portail staff à l’administration de la plateforme, afin que la gestion commerciale et la gestion des données clientes ne partagent pas la même surface d’accès."),
    ],
    "2.3.1 Problématique": [
        ("p", "Trois difficultés structurent le besoin. Premièrement, les systèmes sources utilisent des dialectes et des capacités différentes ; il faut donc normaliser les profils sans masquer les limites de chaque connecteur. Deuxièmement, une alerte utile doit éviter la répétition : plusieurs échecs associés à une table doivent enrichir le même incident tant qu’il reste ouvert. Troisièmement, l’IA générative doit être utile à l’enquête sans devenir l’autorité qui décide de l’existence ou de la gravité de l’incident."),
    ],
    "2.3.2 Solution proposée": [
        ("p", "La réponse retenue est une architecture asynchrone dans laquelle la mesure précède toujours l’interprétation. Un profileur exécute une requête agrégée sur la source, les détecteurs évaluent les métriques persistées, puis le service d’incident applique les règles de sévérité et de déduplication. Ce n’est qu’après cette étape que la narration IA reçoit un contexte borné. Cette séquence préserve une preuve technique indépendante du fournisseur LLM."),
        ("callout", "Principe de conception", "Les règles et détecteurs créent l’incident ; le LLM l’explique. Une narration indisponible ou invalide ne doit jamais effacer le signal technique ni empêcher l’opérateur d’accéder aux mesures."),
    ],
    "2.4.1 Méthode Agile": [
        ("p", "La méthode adoptée reprend les principes de Scrum sans reproduire artificiellement tous les rôles d’une équipe complète. Le backlog est organisé par verticales démontrables, les tâches sont limitées à un résultat observable et chaque fin de sprint comprend une revue des critères d’acceptation. Les anomalies découvertes durant les tests réintègrent le backlog. La documentation et les preuves ne sont pas reportées à la fin : elles font partie de la définition de terminé."),
    ],
    "2.4.2 Organisation en sprints": [
        ("table", "Tableau 1.2", "Découpage des sprints et critères de sortie", ["Sprint", "Objectif", "Critère de sortie"], [
            ["S1", "Cadrage et environnement", "Périmètre, risques et pile locale documentés"],
            ["S2", "Identités et multi-tenancy", "Authentification et isolation testées"],
            ["S3", "Sources et profilage", "Connexion, découverte et profil persistant"],
            ["S4", "Détection et incidents", "Anomalie seedée et incident dédupliqué"],
            ["S5", "Narration et alertes", "Résumé structuré et message livré"],
            ["S6", "Moniteurs et gouvernance", "Révisions traçables et contrôles observe-only"],
            ["S7", "Stabilisation PFE", "Tests, captures, démonstration et rapport"],
        ], [1100, 3700, 4150], "tab_1_2"),
    ],
    "3.2 Approches existantes": [
        ("h3", "2.2.1 Contrôles déclaratifs"),
        ("p", "Les frameworks déclaratifs formalisent les attentes sous forme de règles lisibles et versionnables. Great Expectations associe des Expectations à des lots de données et produit des résultats de validation [11]. SodaCL décrit des métriques et des seuils dans un langage YAML [12]. Cette famille est adaptée aux contrats connus, mais exige que l’équipe explicite les règles et maintienne les seuils lorsque le comportement des données évolue."),
        ("h3", "2.2.2 Détection statistique et apprentissage non supervisé"),
        ("p", "Les seuils statiques sont insuffisants lorsque le volume suit une tendance ou une saisonnalité. Le z-score compare une observation à une moyenne et un écart-type historiques ; Isolation Forest repère des observations rares dans un espace multivarié ; STL sépare tendance, saison et résidu. Ces méthodes réduisent l’effort de configuration, mais nécessitent un historique minimal et peuvent produire des faux positifs lorsque le contexte métier change."),
        ("h3", "2.2.3 Observabilité et gestion d’incidents"),
        ("p", "Une plateforme d’observabilité complète ne se limite pas à exécuter des tests. Elle relie un signal à un actif, conserve l’historique, attribue une sévérité, notifie les responsables et facilite l’investigation. La valeur opérationnelle dépend donc autant de la déduplication, du routage et de la traçabilité que du détecteur lui-même. Cette observation justifie l’orientation de DataWatch vers une verticale allant de la mesure à l’action."),
        ("table", "Tableau 2.1", "Positionnement synthétique des approches", ["Approche", "Point fort", "Limite principale", "Apport retenu"], [
            ["Règles déclaratives", "Lisibles et auditables", "Configuration manuelle", "Moniteurs typés et versionnés"],
            ["Seuils statistiques", "Adaptation à l’historique", "Sensibles aux ruptures de régime", "Z-score et évolution temporelle"],
            ["Apprentissage non supervisé", "Détection multivariée", "Explication plus difficile", "Isolation Forest avec score visible"],
            ["Observabilité SaaS", "Parcours incident intégré", "Coût et dépendance fournisseur", "Incidents, alertes et vues d’enquête"],
            ["Scripts internes", "Adaptation métier rapide", "Maintenance et audit faibles", "Extension SQL bornée et contrôlée"],
        ], [1800, 2250, 2450, 2450], "tab_2_1"),
    ],
    "3.3 Originalité de la solution": [
        ("p", "Le positionnement n’est pas celui d’un remplacement complet des outils industriels. DataWatch constitue un prototype SaaS intégré qui met l’accent sur quatre choix : une isolation explicite par organisation, un profilage agrégé évitant la lecture ligne par ligne, une traçabilité versionnée des moniteurs et une narration IA subordonnée aux faits mesurés. L’interface réunit ces choix dans un parcours unique, exploitable pour la démonstration et pour l’analyse critique."),
        ("p", "La seconde originalité concerne la gouvernance. Les preuves, versions et évaluations sont séparées des états mutables de déploiement. Les contrôles peuvent conclure pass, fail, unknown, unsupported, not applicable ou error ; un manque d’information n’est donc pas transformé artificiellement en conformité. Le mode observe-only rend le risque visible sans bloquer une publication et sans revendiquer une certification juridique."),
    ],
    "4.2.1 Objectifs de la solution": [
        ("p", "L’objectif général est décliné en objectifs mesurables : enregistrer une source sans stocker ses secrets en clair ; produire un profil horodaté et rattaché à une organisation ; expliquer chaque contrôle par une valeur observée et une plage attendue ; conserver un incident unique par table tant que le défaut persiste ; livrer une alerte selon une règle de sévérité ; et présenter une narration structurée qui sépare résumé, causes probables et actions recommandées."),
    ],
    "4.2.2 Besoins fonctionnels": [
        ("table", "Tableau 3.1", "Besoins fonctionnels prioritaires", ["ID", "Besoin", "Critère d’acceptation"], [
            ["BF-01", "Authentifier un utilisateur dans son organisation", "Le contexte tenant est établi avant tout accès métier"],
            ["BF-02", "Enregistrer et tester une source", "Le statut de connexion et l’erreur éventuelle sont visibles"],
            ["BF-03", "Découvrir et surveiller une table", "L’actif est planifié avec intervalle et sensibilité"],
            ["BF-04", "Produire un profil", "Volume, fraîcheur, schéma et métriques colonnes sont persistés"],
            ["BF-05", "Détecter une anomalie", "Chaque résultat contient état, observation et justification"],
            ["BF-06", "Gérer un incident", "Création, acquittement, affectation et résolution sont traçables"],
            ["BF-07", "Alerter les responsables", "Le canal respecte la sévérité minimale configurée"],
            ["BF-08", "Assister l’investigation", "La narration structurée reste distincte des faits mesurés"],
        ], [900, 3200, 4300], "tab_3_1"),
    ],
    "4.2.3 Besoins non fonctionnels": [
        ("table", "Tableau 3.2", "Exigences non fonctionnelles et réponses de conception", ["Exigence", "Risque traité", "Réponse retenue"], [
            ["Sécurité", "Exposition de secrets ou données inter-tenant", "Chiffrement par organisation et filtres tenant"],
            ["Fiabilité", "Doublons et reprises incohérentes", "Idempotence, états explicites et déduplication"],
            ["Performance", "Lecture coûteuse des tables sources", "Agrégats SQL et caches à durée limitée"],
            ["Maintenabilité", "Régression lors d’une évolution", "Contrats typés, migrations et tests automatisés"],
            ["Traçabilité", "Perte du contexte d’une décision", "Révisions immuables et résultats horodatés"],
            ["Utilisabilité", "Surcharge cognitive pendant un incident", "Hiérarchie visuelle et parcours guidé"],
        ], [1800, 3150, 3450], "tab_3_2"),
    ],
    "4.3 Conception de la solution": [
        ("h3", "3.3.1 Acteurs et cas d’utilisation"),
        ("p", "Le diagramme de cas d’utilisation distingue le membre d’une organisation, son administrateur et l’opérateur staff. Le membre consulte les actifs et traite les incidents ; l’administrateur ajoute les sources, configure les tables, les moniteurs et les alertes ; le staff gère le cycle de vie des organisations depuis un portail séparé. Les services externes - bases, fournisseur LLM et canaux de notification - sont représentés comme systèmes secondaires."),
        ("p", "La figure 3.1 montre les relations include entre le profilage, l’exécution des contrôles et la création d’un incident, ainsi que les extensions conditionnelles liées à la narration et à l’alerte. Cette représentation évite de confondre une action utilisateur avec une tâche planifiée. Elle met également en évidence que l’acquittement et la résolution demeurent des décisions humaines."),
    ],
    "4.3.1 Diagramme de séquence": [
        ("p", "Le scénario nominal débute par le déclenchement d’APScheduler. L’API place l’identifiant de la table dans la file Redis ; le worker recharge ensuite la configuration, dérive la clé de déchiffrement de l’organisation et instancie le connecteur. Le profil est persistant avant l’exécution des détecteurs. Si au moins un contrôle échoue, le service d’incident crée ou enrichit l’incident, puis enchaîne narration et notification."),
        ("p", "Deux variantes sont importantes. Si la source est indisponible, l’erreur est enregistrée sans fabriquer de métrique. Si le fournisseur LLM échoue ou renvoie un format invalide, l’incident technique reste consultable et l’échec de narration est explicite. Ce comportement de dégradation garantit que la couche d’assistance ne devient pas un point unique de défaillance."),
    ],
    "4.3.2 Diagramme de classes": [
        ("p", "Le modèle de domaine s’organise autour de l’agrégat Organization. DataSource et MonitoredTable décrivent les actifs ; TableProfile et CheckResult constituent la preuve de mesure ; Incident regroupe les occurrences liées ; AlertConfig exprime le routage. Le sous-domaine des moniteurs sépare Monitor, identité stable, de MonitorRevision, définition append-only, et de MonitorRun, trace d’exécution. Cette séparation évite qu’une modification réécrive l’historique."),
    ],
    "4.4 Architecture proposée": [
        ("h3", "3.4.1 Vue logique en couches"),
        ("p", "La couche présentation regroupe l’application React et ses composants d’état. Elle ne contient pas les règles d’isolation ; chaque appel est contrôlé côté serveur. La couche API expose des contrats REST, valide les entrées et orchestre les services. La couche métier applique profilage, détection, incidents, narration et politiques de plan. La couche d’infrastructure fournit persistance, broker, cache et connecteurs."),
        ("h3", "3.4.2 Exécution asynchrone"),
        ("p", "Le profilage peut dépasser la durée acceptable d’une requête interactive. Il est donc exécuté par Celery. Redis porte la file et certains caches, tandis qu’APScheduler maintient un job par table active. Au redémarrage, les actifs en retard peuvent être remis en file. Les services restent asynchrones et les tâches synchrones utilisent des enveloppes contrôlées, ce qui évite de maintenir deux implémentations métier."),
        ("h3", "3.4.3 Architecture des connecteurs"),
        ("p", "Un contrat BaseConnector uniformise le test de connexion, la découverte, l’introspection et l’exécution de la requête de profil. Les capacités sont déclarées par connecteur plutôt que supposées. PostgreSQL constitue la verticale stable ; DuckDB et SQLite sont positionnés en bêta ; les autres adaptateurs demandent des validations réelles supplémentaires. Ce modèle permet d’étendre le catalogue sans présenter tous les connecteurs comme équivalents."),
    ],
    "4.5 Modèle de données et sécurité": [
        ("h3", "3.5.1 Isolation multi-tenant"),
        ("p", "Chaque entité métier est rattachée directement ou indirectement à une organisation. Les requêtes protégées résolvent le tenant à partir du JWT ou de la clé API, puis filtrent les données selon ce contexte. Des clés étrangères composites renforcent cette preuve au niveau relationnel pour les sous-domaines sensibles. Le portail staff utilise une identité distincte afin d’éviter la confusion entre administration de plateforme et opérations clientes."),
        ("h3", "3.5.2 Protection des secrets"),
        ("p", "Les mots de passe sont hachés et les clés API ne sont montrées qu’à leur création. Les configurations de connexion sont chiffrées avec Fernet ; la clé effective est dérivée du secret maître et de l’identifiant de l’organisation au moyen de HKDF. Ainsi, un chiffré copié d’un tenant vers un autre ne peut pas être déchiffré dans le nouveau contexte. Les journaux et captures évitent les secrets bruts."),
        ("h3", "3.5.3 Intégrité et conservation"),
        ("p", "Les profils et résultats sont horodatés afin de reconstruire l’état ayant mené à un incident. Les révisions de moniteur et les preuves de gouvernance sont immuables lorsque leur valeur d’audit l’exige. Les suppressions ordinaires ne doivent pas effacer silencieusement un registre de preuve. Cette rigueur a un coût en stockage et nécessite, pour une industrialisation, une politique d’export et de rétention gouvernée."),
    ],
    "4.6 Gouvernance de la couche IA": [
        ("p", "Le plan de contrôle distingue l’identité du système IA, ses versions, les usages de données déclarés, les manifestes de release, les déploiements, les approbations, les preuves et les évaluations. Les manifestes sont adressés par leur contenu et l’activation utilise un mécanisme compare-and-swap. Les évaluations référencent précisément la preuve et la version utilisées, ce qui permet de reproduire une décision sans considérer l’état courant comme historique."),
        ("p", "Le périmètre actuel observe une verticale PostgreSQL/pgvector pour les chaînes RAG. Les requêtes sont bornées, exécutées en lecture seule et limitées à des agrégats et métadonnées. Aucune donnée client brute n’est envoyée au registre de preuve. Les états inconnu, non pris en charge ou périmé restent visibles. Ce choix réduit le risque de greenwashing technique et constitue un point de discussion important pour le jury."),
    ],
    "5.2 Workflow proposé": [
        ("h3", "4.2.1 Enregistrement et planification"),
        ("p", "Après validation de la connexion, l’utilisateur choisit une table, un intervalle, une sensibilité et éventuellement une colonne de fraîcheur. La création enregistre l’actif puis programme le contrôle. Un bootstrap d’autopilot peut proposer des contrôles de base à partir du schéma ; les recommandations considérées risquées ou reposant sur du SQL personnalisé sont laissées en attente de revue."),
        ("h3", "4.2.2 Profilage et détection"),
        ("p", "Le profileur construit une requête unique regroupant comptage, fraîcheur, cardinalité et statistiques de colonnes. Le résultat devient un snapshot TableProfile. Les règles déterministes s’appliquent immédiatement ; les méthodes historiques s’activent seulement lorsque le nombre de profils est suffisant. Le score et la plage attendue sont persistés afin que l’interface puisse expliquer pourquoi un contrôle a échoué."),
        ("h3", "4.2.3 Incident, narration et alerte"),
        ("p", "Les échecs sont regroupés par table. Un incident déjà ouvert reçoit la nouvelle occurrence au lieu d’être dupliqué. La sévérité P1 est réservée aux ruptures les plus critiques, notamment table vide ou fraîcheur dépassée ; les dérives de schéma et cumuls d’échecs produisent généralement P2 ; les écarts isolés restent P3. La narration utilise ensuite un contexte compact, validé par un schéma, et les alertes filtrent les routes selon leur seuil minimal."),
    ],
    "5.3 Technologies utilisées": [
        ("table", "Tableau 4.1", "Technologies principales et justification", ["Couche", "Technologie", "Rôle et justification"], [
            ["Interface", "React, Vite, Tailwind", "SPA réactive, composants réutilisables et construction rapide"],
            ["API", "Python 3.12, FastAPI", "Contrats typés, validation Pydantic et I/O asynchrones"],
            ["Persistance", "PostgreSQL 16, SQLAlchemy", "Transactions, contraintes, JSONB et migrations"],
            ["Traitements", "Celery, APScheduler", "Tâches différées et planification par actif"],
            ["Broker/cache", "Redis", "File de tâches, modèles et résultats temporaires"],
            ["IA", "API compatible OpenAI", "Narration structurée avec fournisseur configurable"],
            ["Exploitation", "Docker Compose", "Pile locale reproductible et seed déterministe"],
            ["Validation", "Pytest, Playwright", "Tests de services et parcours navigateur"],
        ], [1600, 2300, 5000], "tab_4_1"),
    ],
    "5.4 Présentation des interfaces": [
        ("p", "La conception visuelle suit une logique de divulgation progressive. L’écran Opérations répond d’abord à trois questions : que se passe-t-il, quel actif est touché et quelle action est prioritaire ? Le détail expose ensuite les signaux, la chronologie et la narration. Les paramètres techniques restent accessibles, mais ne concurrencent pas les éléments nécessaires à la décision immédiate."),
    ],
    "5.5 Tests et validation": [
        ("h3", "4.5.1 Stratégie de test"),
        ("p", "La stratégie combine plusieurs niveaux. Les tests unitaires couvrent les règles, validateurs et transformations pures. Les tests de service vérifient les transactions, autorisations et états. Les tests d’intégration nécessitent PostgreSQL et Redis afin d’exposer les erreurs que les doubles de test masquent. Enfin, Playwright rejoue les parcours visibles sur une pile seedée. La construction frontend et la validation de la configuration Docker complètent ces preuves."),
        ("h3", "4.5.2 Scénarios fonctionnels"),
        ("table", "Tableau 4.2", "Matrice de validation fonctionnelle", ["Scénario", "Résultat attendu", "Preuve"], [
            ["Connexion Acme", "Accès limité au workspace", "Parcours navigateur"],
            ["Ouverture de l’incident orders", "P1, signaux et narration visibles", "Capture et API"],
            ["Profil de la table", "Historique et métriques cohérents", "Capture et base seedée"],
            ["Alerte e-mail", "Message acheminé vers MailHog", "Interface et boîte de test"],
            ["Moniteur typé", "Révision validée et résultat traçable", "Tests backend"],
            ["Gouvernance IA", "États et preuves observe-only visibles", "Playwright et ledger"],
        ], [2600, 3550, 2750], "tab_4_2"),
        ("h3", "4.5.3 Résultats et interprétation"),
        ("p", "La session de validation du rapport a démarré une pile Docker, réinitialisé les données et rejoué les cinq parcours de démonstration. La suite backend a produit plusieurs centaines de succès, mais elle a également révélé des tests ignorés et des échecs dépendant du montage complet du dépôt. Ces résultats sont présentés comme une photographie reproductible de l’environnement local, et non comme une garantie universelle."),
        ("p", "La distinction entre test syntaxique, test unitaire et preuve d’intégration est essentielle. Une configuration Docker valide ne prouve pas que les services démarrent ; une suite avec dépendances simulées ne prouve pas qu’une transaction réelle fonctionne ; une capture correcte ne prouve pas la résistance à la charge. Le rapport conserve donc les limites à proximité des résultats afin d’éviter une conclusion surévaluée."),
    ],
    "5.6 Discussion des limites": [
        ("p", "Le premier risque concerne la profondeur des connecteurs. Un adaptateur peut satisfaire un contrat abstrait sans avoir été validé avec des identifiants réels, des volumes représentatifs et les particularités de son dialecte. Le catalogue distingue donc stable, bêta et expérimental. L’industrialisation demanderait une matrice de conformité exécutée pour chaque version de moteur et une surveillance des coûts de requête."),
        ("p", "Le deuxième risque concerne la détection. Les seuils et modèles utilisent un historique limité ; ils ne disposent pas d’un jeu annoté permettant de mesurer précision, rappel et taux de faux positifs. Le troisième concerne la narration : la validation de schéma garantit une structure, pas l’exactitude des hypothèses. Un mécanisme de retour humain, une évaluation par scénario et des garde-fous sur les données transmises restent nécessaires."),
        ("p", "Enfin, la preuve locale ne couvre ni montée en charge multi-région, ni reprise après sinistre, ni engagement de disponibilité, ni conformité réglementaire. Le mode observe-only de la gouvernance IA est intentionnel : il rend des lacunes visibles, mais ne bloque pas une release. Ces limites n’invalident pas le prototype ; elles définissent précisément le travail requis pour passer d’un PFE démontrable à un service commercial fiable."),
    ],
    "6.2 Synthèse des apports": [
        ("p", "Sur le plan technique, le projet apporte une architecture cohérente reliant connecteurs, profilage, détection, incident, narration et alerte. Sur le plan méthodologique, il impose une discipline de preuve : capacités déclarées, états explicites, révisions immuables et résultats reproductibles. Sur le plan utilisateur, il transforme une série de métriques en parcours d’investigation. Le principal apprentissage est qu’une solution de qualité des données devient utile lorsque la détection, le contexte et la responsabilité sont traités ensemble."),
    ],
}

# Visual evidence is attached to the section that explains it. This keeps the
# report readable: one argument, one figure, then the interpretation.
ENRICHMENTS.setdefault("2.4.3 Diagramme de Gantt et jalons", []).extend([
    ("p", "Le calendrier ne simule pas une succession parfaitement linéaire. L’architecture démarre pendant le cadrage ; la détection chevauche le profilage ; les tests commencent avant la fermeture fonctionnelle. La ligne rouge du 31 août borne la période évaluée. Au-delà, la barre grise assume le statut réel du projet : le produit continue."),
    ("figure", "Figure 1.1"),
])
ENRICHMENTS.setdefault("4.3 Conception de la solution", []).extend([
    ("figure", "Figure 3.1"), ("figure", "Figure 3.2"), ("figure", "Figure 3.3"),
])
ENRICHMENTS.setdefault("4.3.1 Diagramme de séquence", []).extend([
    ("figure", "Figure 3.4"), ("figure", "Figure 3.5"), ("figure", "Figure 3.6"),
    ("figure", "Figure 3.7"), ("figure", "Figure 3.8"),
])
ENRICHMENTS.setdefault("4.3.2 Diagramme de classes", []).extend([
    ("p", "Quatre vues remplacent un diagramme monolithique devenu illisible sur A4. Elles conservent les cardinalités et les frontières de domaine : surveillance, collaboration, moniteurs versionnés, puis gouvernance IA."),
    ("figure", "Figure 3.9"), ("figure", "Figure 3.10"), ("figure", "Figure 3.11"), ("figure", "Figure 3.12"),
])
ENRICHMENTS.setdefault("4.4 Architecture proposée", []).extend([
    ("figure", "Figure 3.13"), ("figure", "Figure 3.14"),
])
ENRICHMENTS.setdefault("4.5 Modèle de données et sécurité", []).extend([
    ("h3", "3.5.4 Structure relationnelle complète"),
    ("p", "Le schéma physique compte 29 tables applicatives. La vue d’ensemble révèle quatre masses nettes : identité et collaboration, surveillance, moniteurs typés, gouvernance IA. Trois vues relationnelles détaillées suivent. Le dictionnaire exhaustif — colonnes, types, nullabilité, clés et effectifs seedés — est reporté en annexe afin de garder ce chapitre respirable."),
    ("figure", "Figure 3.15"), ("figure", "Figure 3.16"), ("figure", "Figure 3.17"), ("figure", "Figure 3.18"),
])
ENRICHMENTS.setdefault("5.4.1 Vue Opérations", []).extend([
    ("p", "Le parcours commence avant le tableau de bord. Le sous-domaine dans l’URL fixe le workspace ; la page de connexion reste volontairement sobre. Une fois authentifié, l’opérateur reçoit la file priorisée et le catalogue des actifs, pas un mur de graphiques décoratifs."),
    ("figure", "Figure 4.1"), ("figure", "Figure 4.2"), ("figure", "Figure 4.3"),
])
ENRICHMENTS.setdefault("5.4.2 Détail de l’incident P1", []).extend([
    ("p", "L’enquête tient sur trois plans : la liste situe l’urgence, le détail rassemble les faits horodatés, puis la narration IA propose des pistes clairement séparées des mesures. L’opérateur garde la décision — affecter, acquitter, résoudre ou documenter un faux positif."),
    ("figure", "Figure 4.4"), ("figure", "Figure 4.5"), ("figure", "Figure 4.6"),
])
ENRICHMENTS.setdefault("5.4.3 Détail de la table surveillée", []).extend([
    ("p", "La fiche public.orders relie série temporelle, contrôles et configuration. Les recommandations ne s’activent pas en silence : elles conduisent vers le catalogue des moniteurs et un constructeur DSL qui expose définition, mode et validation."),
    ("figure", "Figure 4.7"), ("figure", "Figure 4.8"), ("figure", "Figure 4.9"), ("figure", "Figure 4.10"),
])
ENRICHMENTS.setdefault("5.4.4 Alertes et gouvernance IA", []).extend([
    ("h3", "4.4.4.1 Rapports, équipes et astreintes"),
    ("p", "La réponse à l’incident dépasse l’écran technique. Les rapports condensent une semaine ; les équipes rendent l’affectation concrète ; les créneaux d’astreinte indiquent qui peut réellement recevoir une escalade."),
    ("figure", "Figure 4.11"), ("figure", "Figure 4.12"), ("figure", "Figure 4.13"),
    ("h3", "4.4.4.2 Sources, connecteurs et notifications"),
    ("p", "Le catalogue distingue les capacités annoncées de chaque moteur. La source seedée sert de verticale vérifiée ; le routage et les préférences montrent ensuite comment la même alerte se distribue sans imposer un canal unique."),
    ("figure", "Figure 4.14"), ("figure", "Figure 4.15"), ("figure", "Figure 4.16"), ("figure", "Figure 4.17"),
    ("h3", "4.4.4.3 Registre de gouvernance IA"),
    ("p", "La gouvernance IA désigne ici l’ensemble des responsabilités, versions, déclarations de données et preuves nécessaires pour répondre à cinq questions simples : quel système fonctionne, dans quel but déclaré, avec quelles données, sous la responsabilité de qui, et avec quels contrôles disponibles ? DataWatch matérialise ces réponses dans un registre isolé par organisation. Les versions, manifestes et évaluations terminales sont immuables ; les états inconnus ou périmés restent visibles au lieu d’être maquillés en succès."),
    ("p", "Dans le scénario Acme, un assistant RAG de support est lié à une table surveillée et à une empreinte de schéma. À chaque profil réussi, DataWatch peut réévaluer l’âge des preuves, la fraîcheur du schéma, la présence de responsables, les rôles d’accès déclarés et quelques incohérences vectorielles. L’écran rassemble ensuite état global, confiance des preuves, risque résiduel, raisons de contrôle et chronologie. Il aide un opérateur à voir ce qui manque. Rien de plus."),
    ("figure", "Figure 4.18"), ("figure", "Figure 4.19"), ("figure", "Figure 4.20"),
    ("h3", "4.4.4.4 Limites du prototype de gouvernance IA"),
    ("p", "Cette brique est une preuve de concept, volontairement petite. La démonstration repose sur un seul système IA seedé, une verticale PostgreSQL/pgvector et des anomalies préparées pour être reproductibles. Plusieurs informations demeurent des déclarations client ; elles ne prouvent ni l’usage réel des données, ni la finalité juridique, ni le comportement effectif du modèle. Le prototype ne mesure pas la robustesse, les biais, l’équité, la sécurité adversariale ou la dérive des sorties. Il ne lit d’ailleurs ni prompts, ni réponses, ni lignes métier : le registre conserve uniquement des métadonnées bornées."),
    ("p", "Le mode observe-only est la frontière la plus importante. Un contrôle en échec ouvre un signal et peut déclencher une alerte, mais il n’empêche pas une release. L’interface actuelle permet surtout d’enregistrer un système puis de consulter le scénario préparé ; la création complète des versions, usages, manifestes, approbations et politiques n’est pas encore un parcours SaaS abouti. Pour devenir une fonction produit crédible, il faudra un éditeur de bout en bout, des gates d’approbation configurables, un véritable circuit de revue humaine, des exports d’audit, une politique de rétention, des contrôles multi-fournisseurs et des validations répétées sur des cas non seedés."),
    ("h3", "4.4.4.5 Portail staff"),
    ("p", "L’administration de la plateforme utilise une authentification séparée. Le staff voit les organisations, les usages et l’état d’un tenant ; il n’emprunte pas l’identité d’un membre du workspace."),
    ("figure", "Figure 4.21"), ("figure", "Figure 4.22"), ("figure", "Figure 4.23"), ("figure", "Figure 4.24"),
])


def add_enrichments(doc, heading, bookmark_id):
    for action in ENRICHMENTS.get(heading, []):
        kind = action[0]
        if kind == "p":
            add_body(doc, action[1])
        elif kind == "h2":
            add_heading(doc, action[1], 2, anchor=heading_anchor(action[1]), bookmark_id=bookmark_id)
            bookmark_id += 1
        elif kind == "h3":
            add_heading(doc, action[1], 3, anchor=heading_anchor(action[1]), bookmark_id=bookmark_id)
            bookmark_id += 1
        elif kind == "callout":
            add_callout(doc, action[1], action[2])
        elif kind == "table":
            _, label, caption, headers, rows, widths, anchor = action
            bookmark_id = add_academic_table(doc, label, caption, headers, rows, widths, anchor, bookmark_id)
        elif kind == "figure":
            label = action[1]
            caption, path = FIGURE_META[label]
            anchor = "fig_" + label.split()[1].replace(".", "_")
            add_picture(doc, path, label, caption, anchor=anchor, bookmark_id=bookmark_id)
            bookmark_id += 1
    return bookmark_id


def build():
    data = json.loads(SOURCE.read_text())
    database_evidence = json.loads(DATABASE_EVIDENCE.read_text())
    paras = data["paragraphs"]
    doc = Document()
    configure_styles(doc)
    bullet_num, decimal_num = add_numbering(doc)
    update_fields_on_open(doc)

    cover_sec = doc.sections[0]; section_geometry(cover_sec); set_header(cover_sec); set_footer(cover_sec, numbered=False)
    cover(doc)

    pre = doc.add_section(WD_SECTION_START.NEW_PAGE); section_geometry(pre); set_page_numbering(pre, "lowerRoman", 1); set_header(pre); set_footer(pre, numbered=True)
    bookmark_id = 100
    for i in range(10, 25):
        text = paras[i]["text"].strip()
        if not text: continue
        if paras[i].get("namedStyleType") == "HEADING_1":
            add_heading(doc, text, 1, front=True, anchor=f"front_{i}", bookmark_id=bookmark_id); bookmark_id += 1
        elif i == 11:
            for _ in range(5): doc.add_paragraph()
            add_body(doc, text, align=WD_ALIGN_PARAGRAPH.CENTER, italic=True)
        elif i in (19, 24):
            p = doc.add_paragraph(); p.alignment = WD_ALIGN_PARAGRAPH.LEFT; p.paragraph_format.space_before = Pt(8)
            label, value = text.split(":", 1)
            r = p.add_run(label + " :"); set_font(r, 10, bold=True, color=ACCENT)
            r = p.add_run(value); set_font(r, 10, italic=True, color=INK)
        else:
            add_body(doc, text)

    page_map = json.loads(PAGE_MAP_PATH.read_text()) if PAGE_MAP_PATH.exists() else {}
    toc_entries = [
        ("I. Dédicace", "i", "front_10", 1), ("II. Remerciements", "ii", "front_12", 1),
        ("III. Résumé", "iii", "front_15", 1), ("IV. Abstract", "iv", "front_20", 1),
        ("V. Table des matières", page_map.get("V. Table des matières", "v"), "front_toc", 1),
        ("VI. Liste des figures", page_map.get("VI. Liste des figures", "vii"), "front_figures", 1),
        ("VII. Liste des tableaux", page_map.get("VII. Liste des tableaux", "viii"), "front_tables", 1),
        ("VIII. Liste des abréviations", page_map.get("VIII. Liste des abréviations", "ix"), "front_abbr", 1),
    ]
    for i in range(118, len(paras)):
        style = paras[i].get("namedStyleType")
        if style not in ("HEADING_1", "HEADING_2", "HEADING_3"):
            continue
        source_heading = paras[i]["text"].strip()
        rendered = remap_heading(source_heading)
        level = {"HEADING_1": 1, "HEADING_2": 2, "HEADING_3": 3}[style]
        toc_entries.append((rendered, page_map.get(rendered, ""), f"body_{i}", level))
        for action in ENRICHMENTS.get(source_heading, []):
            if action[0] in ("h2", "h3"):
                extra_level = 2 if action[0] == "h2" else 3
                toc_entries.append((action[1], page_map.get(action[1], ""), heading_anchor(action[1]), extra_level))
    toc_entries.extend([
        ("Annexe D — Dictionnaire du modèle de données", page_map.get("Annexe D — Dictionnaire du modèle de données", ""), "annex_d", 2),
        ("Annexe E — État du jeu de démonstration", page_map.get("Annexe E — État du jeu de démonstration", ""), "annex_e", 2),
        ("Annexe F — Commandes de reproduction", page_map.get("Annexe F — Commandes de reproduction", ""), "annex_f", 2),
    ])

    add_heading(doc, "V. Table des matières", 1, front=True, anchor="front_toc", bookmark_id=bookmark_id); bookmark_id += 1
    add_live_index(doc, toc_entries, 'TOC \\o "1-3" \\h \\z \\u')
    add_heading(doc, "VI. Liste des figures", 1, front=True, anchor="front_figures", bookmark_id=bookmark_id); bookmark_id += 1
    figure_entries = []
    current_chapter = None
    chapter_titles = {"1": "Chapitre 1 — Cadre général", "3": "Chapitre 3 — Analyse et conception", "4": "Chapitre 4 — Réalisation et validation"}
    for label, caption, _ in FIGURE_CATALOG:
        chapter = label.split()[1].split(".")[0]
        if chapter != current_chapter:
            figure_entries.append((chapter_titles[chapter], "", None, 0))
            current_chapter = chapter
        anchor = "fig_" + label.split()[1].replace(".", "_")
        figure_entries.append((f"{label} — {caption}", page_map.get(label, ""), anchor, 2))
    add_static_index(doc, figure_entries)
    add_heading(doc, "VII. Liste des tableaux", 1, front=True, anchor="front_tables", bookmark_id=bookmark_id); bookmark_id += 1
    table_entries = [
        ("Chapitre 1 — Cadre général", "", None, 0),
        ("Tableau 1.1 — Acteurs et responsabilités du projet", page_map.get("Tableau 1.1", ""), "tab_1_1", 2),
        ("Tableau 1.2 — Découpage des sprints et critères de sortie", page_map.get("Tableau 1.2", ""), "tab_1_2", 2),
        ("Chapitre 2 — État de l’art", "", None, 0),
        ("Tableau 2.1 — Positionnement synthétique des approches", page_map.get("Tableau 2.1", ""), "tab_2_1", 2),
        ("Chapitre 3 — Analyse et conception", "", None, 0),
        ("Tableau 3.1 — Besoins fonctionnels prioritaires", page_map.get("Tableau 3.1", ""), "tab_3_1", 2),
        ("Tableau 3.2 — Exigences non fonctionnelles et réponses", page_map.get("Tableau 3.2", ""), "tab_3_2", 2),
        ("Chapitre 4 — Réalisation et validation", "", None, 0),
        ("Tableau 4.1 — Technologies principales et justification", page_map.get("Tableau 4.1", ""), "tab_4_1", 2),
        ("Tableau 4.2 — Matrice de validation fonctionnelle", page_map.get("Tableau 4.2", ""), "tab_4_2", 2),
        ("Annexes", "", None, 0),
    ]
    for index, table_info in enumerate(database_evidence["tables"], 1):
        label = f"Tableau D.{index}"
        table_entries.append((f"{label} — Structure de {table_info['name']}", page_map.get(label, ""), f"tab_d_{index}", 2))
    table_entries.append(("Tableau E.1 — Effectifs du jeu de démonstration", page_map.get("Tableau E.1", ""), "tab_e_1", 2))
    for index, (_, caption) in enumerate(SAMPLE_TABLES, 2):
        label = f"Tableau E.{index}"
        table_entries.append((f"{label} — {caption}", page_map.get(label, ""), f"tab_e_{index}", 2))
    add_static_index(doc, table_entries)
    add_heading(doc, "VIII. Liste des abréviations", 1, front=True, anchor="front_abbr", bookmark_id=bookmark_id); bookmark_id += 1
    add_abbreviations(doc)

    body = doc.add_section(WD_SECTION_START.NEW_PAGE); section_geometry(body); set_page_numbering(body, "decimal", 1); set_header(body, "DataWatch — Rapport de Projet de Fin d’Études"); set_footer(body, numbered=True)

    extras = {
        "3.3 Originalité de la solution": [
            "Le DSL de moniteurs complète cette chaîne par des définitions strictes, versionnées et liées au schéma observé. Une révision est validée puis prévisualisée avant activation ; l’exécution utilise un plan déterministe et un état d’évaluation séparé de l’historique immuable. Ce choix évite qu’une modification silencieuse change le comportement d’un contrôle déjà audité.",
        ],
        "4.4 Architecture proposée": [
            "Le cycle de profilage démarre dans APScheduler, qui place une tâche dans Redis. Celery déchiffre la configuration de la source dans le contexte de l’organisation, construit une requête agrégée, persiste le profil, puis déclenche les détecteurs et les moniteurs personnalisés. La narration et l’alerte sont exécutées après la persistance de l’incident afin qu’un échec externe ne supprime pas le fait technique observé.",
        ],
        "4.5 Modèle de données et sécurité": [
            "La sécurité repose également sur des clés étrangères composites qui prouvent l’appartenance des entités à une même organisation. Les révisions, résultats terminaux et preuves de gouvernance sont append-only lorsque leur valeur d’audit doit être conservée. Les clés API sont stockées sous forme de hachage et les secrets de connexion sont chiffrés avec une clé dérivée par organisation.",
        ],
        "5.3 Technologies utilisées": [
            "Le choix des technologies répond à une logique de responsabilités clairement séparées : FastAPI pour les contrats et l’asynchronisme, PostgreSQL pour les contraintes transactionnelles et l’historique, Redis et Celery pour les travaux différés, React pour l’investigation visible, et Docker Compose pour reproduire l’environnement de démonstration. Cette organisation facilite l’évolution indépendante des composants tout en conservant un parcours de bout en bout testable.",
        ],
    }

    for i in range(118, len(paras)):
        if i in SKIP_BODY_INDEXES: continue
        text = paras[i]["text"].strip()
        if not text: continue
        style = paras[i].get("namedStyleType")
        if i == 146:
            text = "Le planning associe chaque incrément à un objectif vérifiable et à un livrable exploitable dans la démonstration. La figure 1.1 synthétise les sept sprints, leurs chevauchements et leurs principaux jalons."
        if i in range(147, 152):
            continue
        fig = re.match(r"^(Figure \d+\.\d+)\s*[-–—]\s*(.+?)\.?$", text)
        if fig:
            label, caption = fig.group(1), fig.group(2)
            source_label = label
            if label == "Figure 4.7": label = "Figure 4.6"
            elif label == "Figure 4.6": label = "Figure 4.7"
            add_picture(doc, FIGURES[source_label], label, caption, anchor="fig_" + label.split()[1].replace(".", "_"), bookmark_id=bookmark_id); bookmark_id += 1
            continue
        if style in ("HEADING_1", "HEADING_2", "HEADING_3"):
            level = {"HEADING_1": 1, "HEADING_2": 2, "HEADING_3": 3}[style]
            anchor = f"body_{i}"
            add_heading(doc, remap_heading(text), level, anchor=anchor, bookmark_id=bookmark_id)
            bookmark_id += 1
            bookmark_id = add_enrichments(doc, text, bookmark_id)
            for extra in extras.get(text, []): add_body(doc, extra)
            continue
        if i in range(271, 280):
            p = add_body(doc, text, align=WD_ALIGN_PARAGRAPH.LEFT, after=5)
            p.paragraph_format.left_indent = Cm(0.7); p.paragraph_format.first_line_indent = Cm(-0.7)
            for run in p.runs: set_font(run, 9.7, color=INK)
            if i == 279:
                extra_refs = [
                    "[10] ISGA, École d’ingénieur — campus Casablanca, présentation du cycle et de la spécialisation Intelligence Artificielle et Big Data, consultée en septembre 2026. https://info.isga.ma/ecole-ingenieur-casablanca",
                    "[11] Great Expectations, Run Validations — documentation officielle, consultée en septembre 2026. https://docs.greatexpectations.io/docs/core/run_validations/",
                    "[12] Soda, SodaCL metrics and checks — documentation officielle, consultée en septembre 2026. https://docs.soda.io/soda-cl/metrics-and-checks.html",
                ]
                for ref in extra_refs:
                    rp = add_body(doc, ref, align=WD_ALIGN_PARAGRAPH.LEFT, after=5)
                    rp.paragraph_format.left_indent = Cm(0.7); rp.paragraph_format.first_line_indent = Cm(-0.7)
                    for run in rp.runs: set_font(run, 9.7, color=INK)
            continue
        if is_bullet_index(i):
            add_list(doc, text, bullet_num)
            continue
        if i in range(282, 287):
            add_list(doc, text, decimal_num)
            continue
        if i == 249:
            p = add_body(doc, text.upper(), align=WD_ALIGN_PARAGRAPH.LEFT, bold=True, after=6)
            p.paragraph_format.space_before = Pt(6)
            paragraph_border(p, color=ACCENT, size="6", space="4")
            continue
        add_body(doc, text)

    doc.add_page_break()
    add_heading(doc, "Annexe D — Dictionnaire du modèle de données", 2, anchor="annex_d", bookmark_id=bookmark_id); bookmark_id += 1
    add_body(doc, "Cette annexe décrit les 29 tables applicatives réellement chargées par SQLAlchemy. La table technique alembic_version est exclue. Chaque ligne provient des métadonnées du code : aucun champ n’a été reconstitué à la main. Les références multiples matérialisent les contraintes composites employées pour maintenir l’isolation entre organisations.")
    for index, table_info in enumerate(database_evidence["tables"], 1):
        rows = []
        unique_columns = {column for constraint in table_info.get("unique_constraints", []) for column in constraint}
        for column in table_info["columns"]:
            flags = []
            if column["primary_key"]: flags.append("PK")
            flags.append("facultatif" if column["nullable"] else "obligatoire")
            if column["name"] in unique_columns: flags.append("unicité composée")
            rows.append([
                column["name"], column["type"], ", ".join(flags),
                ", ".join(column["foreign_keys"]) if column["foreign_keys"] else "—",
            ])
        label = f"Tableau D.{index}"
        caption = f"Structure de {table_info['name']} — {table_info['responsibility']}"
        bookmark_id = add_academic_table(
            doc, label, caption, ["Colonne", "Type", "Contraintes", "Référence(s)"],
            rows, [2050, 1900, 2250, 2700], f"tab_d_{index}", bookmark_id,
        )

    doc.add_page_break()
    add_heading(doc, "Annexe E — État du jeu de démonstration", 2, anchor="annex_e", bookmark_id=bookmark_id); bookmark_id += 1
    total_rows = sum(database_evidence["seeded_row_counts"].values())
    add_body(doc, f"Le seed contrôlé contient {total_rows} lignes applicatives. Sa densité n’est pas uniforme : 463 profils et 376 résultats de contrôle donnent de la matière aux courbes, tandis que les entités de configuration restent volontairement peu nombreuses. Les extraits ci-dessous retirent mots de passe, clés, jetons et configurations chiffrées.")
    counts = sorted(database_evidence["seeded_row_counts"].items(), key=lambda item: (-item[1], item[0]))
    bookmark_id = add_academic_table(
        doc, "Tableau E.1", "Effectifs du jeu de démonstration", ["Table", "Lignes", "Lecture"],
        [[name, str(count), "historique dense" if count >= 100 else ("scénario présent" if count else "structure prête, non seedée")] for name, count in counts],
        [3500, 1200, 4200], "tab_e_1", bookmark_id,
    )
    for index, (sample_key, caption) in enumerate(SAMPLE_TABLES, 2):
        sample_rows = database_evidence["non_sensitive_seed_samples"].get(sample_key, [])
        if not sample_rows:
            continue
        headers = list(sample_rows[0].keys())
        values = [[str(row.get(header, "—")) for header in headers] for row in sample_rows]
        widths = [8950 // len(headers)] * len(headers)
        widths[-1] += 8950 - sum(widths)
        bookmark_id = add_academic_table(
            doc, f"Tableau E.{index}", caption, headers, values, widths, f"tab_e_{index}", bookmark_id,
        )

    doc.add_page_break()
    add_heading(doc, "Annexe F — Commandes de reproduction", 2, anchor="annex_f", bookmark_id=bookmark_id); bookmark_id += 1
    add_body(doc, "Les commandes suivantes reconstruisent la pile, réinitialisent les données, réexportent la preuve du schéma et régénèrent les 24 vues du rapport. Les identifiants de démonstration restent dans le guide local ; ils ne constituent pas des secrets de production.")
    add_code_block(doc, [
        "docker compose up -d --wait",
        "docker compose --profile seed run --rm --entrypoint python seed /scripts/quickstart.py --reset",
        "curl -fsS http://localhost:8000/ready",
        "python scripts/pfe/export_database_evidence.py",
        "python scripts/pfe/generate_report_visuals.py",
        "cd frontend && npm run capture:pfe",
    ])

    core = doc.core_properties
    core.title = "Rapport PFE — DataWatch"
    core.subject = "Conception et réalisation d’une plateforme SaaS de surveillance de la qualité des données"
    core.author = "Mounir Gaiby"
    core.keywords = "DataWatch, qualité des données, SaaS, intelligence artificielle, ISGA"
    core.comments = "Rapport de Projet de Fin d’Études — ISGA Casablanca"

    OUT.parent.mkdir(parents=True, exist_ok=True)
    doc.save(OUT)
    print(OUT)


if __name__ == "__main__":
    build()
