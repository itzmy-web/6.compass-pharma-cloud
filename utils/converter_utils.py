# 文件格式转换的工具模块
from utils.logger_utils import logger
from pathlib import Path
import markdown

# [云端兼容] pywin32 仅 Windows 可安装；Linux/云端环境缺此包时降级到 ReportLab 引擎
try:
    import win32com.client
    import pythoncom
    _WORD_COM_AVAILABLE = True
except ImportError:
    win32com = None
    pythoncom = None
    _WORD_COM_AVAILABLE = False

def convert_md_to_pdf_via_word(md_abs_path: Path, pdf_abs_path: Path) -> str:
    """
    使用 Microsoft Word COM 接口将 Markdown 转换为 PDF。
    依赖：pywin32, markdown
    """
    temp_html_path = md_abs_path.with_suffix('.temp.html')
    word_app = None

    if not _WORD_COM_AVAILABLE:
        return "当前环境未安装 pywin32（非 Windows 或云端环境），无法使用 Word 引擎"

    try:
        # 1. MD 转 HTML
        with open(md_abs_path, 'r', encoding='utf-8') as f:
            md_content = f.read()

        html_body = markdown.markdown(md_content, extensions=['tables', 'fenced_code'])
        html_content = f"""
        <html>
        <head>
            <meta charset="UTF-8">
            <style>
                body {{ font-family: "Microsoft YaHei", "SimHei", sans-serif; }}
                table {{ border-collapse: collapse; width: 100%; }}
                th, td {{ border: 1px solid black; padding: 8px; }}
                pre {{ background-color: #f5f5f5; padding: 10px; border-radius: 4px; }}
                code {{ font-family: "Consolas", "Monaco", monospace; }}
            </style>
        </head>
        <body>
            {html_body}
        </body>
        </html>
        """

        with open(temp_html_path, 'w', encoding='utf-8') as f:
            f.write(html_content)

        # 2. 调用 Word COM
        pythoncom.CoInitialize()
        word_app = win32com.client.Dispatch('Word.Application')
        word_app.Visible = False
        word_app.DisplayAlerts = False

        doc = word_app.Documents.Open(str(temp_html_path.resolve()))
        doc.SaveAs(str(pdf_abs_path.resolve()), FileFormat=17)  # wdFormatPDF = 17
        doc.Close(SaveChanges=0)

        if pdf_abs_path.exists():
            return f"成功转换: {pdf_abs_path} (Word引擎)"
        else:
            return f"转换完成但未生成文件: {pdf_abs_path}"

    except ImportError:
        return "缺少依赖库，请安装: pip install pywin32 markdown"
    except Exception as e:
        logger.error(f"Word转换PDF失败: {e}", exc_info=True)
        return f"转换失败: {str(e)}"
    finally:
        # 3. 资源清理
        if word_app:
            try:
                word_app.Quit()
            except Exception as e:
                logger.warning(f"关闭Word应用时出错: {e}")

        if temp_html_path.exists():
            try:
                temp_html_path.unlink()
            except Exception as e:
                logger.warning(f"删除临时HTML文件时出错: {e}")

        try:
            if pythoncom is not None:
                pythoncom.CoUninitialize()
        except Exception as e:
            logger.warning(f"释放COM初始化时出错: {e}")


def convert_md_to_pdf(
        md_abs_path: Path, pdf_abs_path: Path
) -> str:
    """
    自动选择转换引擎：
    1. 优先使用 Microsoft Word（排版/字体还原度最好）
    2. Word 不可用时（如未安装 Office、Linux 服务器），自动降级到纯 Python 的 ReportLab 方案
    返回字符串均以「成功」开头表示成功，便于调用方判断是否需降级。
    """
    word_result = convert_md_to_pdf_via_word(md_abs_path, pdf_abs_path)
    if word_result.startswith("成功"):
        return word_result
    logger.warning(f"Word 引擎不可用，降级到 ReportLab 纯 Python 方案。Word 原因: {word_result}")
    return convert_md_to_pdf_via_reportlab(md_abs_path, pdf_abs_path)


def convert_md_to_pdf_via_reportlab(md_abs_path: Path, pdf_abs_path: Path) -> str:
    """
    纯 Python 方案：Markdown -> ReportLab -> PDF。
    不依赖 Microsoft Word，因此可在未安装 Office 的 Windows / Linux 服务器上运行。
    中文使用 ReportLab 内置的 STSong-Light 字体（无需额外字体文件）。
    """
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer,
                                        Table, TableStyle, Preformatted)
        from reportlab.lib import colors
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.cidfonts import UnicodeCIDFont
        from xml.sax.saxutils import escape as _esc
    except ImportError:
        return "缺少依赖库，请安装: pip install reportlab"

    cn_font = "STSong-Light"
    try:
        pdfmetrics.registerFont(UnicodeCIDFont(cn_font))
    except Exception:
        cn_font = "Helvetica"

    try:
        with open(md_abs_path, "r", encoding="utf-8") as f:
            md_content = f.read()
    except Exception as e:
        return f"读取源文件失败: {e}"

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle("TitleCN", parent=styles["Title"], fontName=cn_font, fontSize=18, leading=24)
    h1 = ParagraphStyle("H1CN", parent=styles["Heading1"], fontName=cn_font, fontSize=15, leading=20)
    h2 = ParagraphStyle("H2CN", parent=styles["Heading2"], fontName=cn_font, fontSize=13, leading=18)
    h3 = ParagraphStyle("H3CN", parent=styles["Heading3"], fontName=cn_font, fontSize=11.5, leading=16)
    body = ParagraphStyle("BodyCN", parent=styles["BodyText"], fontName=cn_font, fontSize=10.5, leading=15)
    code_style = ParagraphStyle("CodeCN", parent=styles["Code"], fontName="Courier", fontSize=9, leading=12)
    list_style = ParagraphStyle("ListCN", parent=body, leftIndent=14, bulletIndent=4)

    def _parse_table_row(line: str):
        return [c.strip() for c in line.strip().strip("|").split("|")]

    flow = []
    lines = md_content.split("\n")
    i, n = 0, len(lines)
    while i < n:
        line = lines[i]
        stripped = line.lstrip()

        # 代码块
        if stripped.startswith("```"):
            i += 1
            buf = []
            while i < n and not lines[i].strip().startswith("```"):
                buf.append(lines[i])
                i += 1
            i += 1
            flow.append(Preformatted("\n".join(buf), code_style))
            flow.append(Spacer(1, 6))
            continue

        # 标题
        if stripped.startswith("#"):
            level = len(stripped) - len(stripped.lstrip("#"))
            text = stripped[level:].strip()
            st = {1: title_style, 2: h1, 3: h2}.get(level, h3)
            flow.append(Paragraph(_esc(text), st))
            flow.append(Spacer(1, 4))
            i += 1
            continue

        # 表格
        if stripped.startswith("|") and "|" in stripped[1:]:
            rows = []
            while i < n and lines[i].lstrip().startswith("|") and "|" in lines[i].lstrip()[1:]:
                rows.append(_parse_table_row(lines[i]))
                i += 1
            if len(rows) >= 2 and all(set(c) <= set("-: ") for c in rows[1]):
                rows = [rows[0]] + rows[2:]
            data = [[Paragraph(_esc(c), body) for c in r] for r in rows]
            t = Table(data, hAlign="LEFT")
            t.setStyle(TableStyle([
                ("GRID", (0, 0), (-1, -1), 0.5, colors.black),
                ("BACKGROUND", (0, 0), (-1, 0), colors.Color(0.9, 0.9, 0.9)),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
            ]))
            flow.append(t)
            flow.append(Spacer(1, 6))
            continue

        # 列表
        if stripped.startswith("- ") or stripped.startswith("* "):
            flow.append(Paragraph("• " + _esc(stripped[2:].strip()), list_style))
            i += 1
            continue

        # 空行
        if not line.strip():
            i += 1
            continue

        # 普通段落（合并连续文本行）
        para = [line]
        i += 1
        while (i < n and lines[i].strip()
               and not lines[i].lstrip().startswith("#")
               and not lines[i].lstrip().startswith("- ")
               and not lines[i].lstrip().startswith("* ")
               and not (lines[i].lstrip().startswith("|") and "|" in lines[i].lstrip()[1:])
               and not lines[i].strip().startswith("```")):
            para.append(lines[i])
            i += 1
        flow.append(Paragraph(_esc(" ".join(para)), body))
        flow.append(Spacer(1, 4))

    doc = SimpleDocTemplate(str(pdf_abs_path), pagesize=A4,
                            leftMargin=50, rightMargin=50, topMargin=50, bottomMargin=50)
    doc.build(flow)

    if pdf_abs_path.exists():
        return f"成功转换: {pdf_abs_path} (ReportLab引擎)"
    return f"转换完成但未生成文件: {pdf_abs_path}"