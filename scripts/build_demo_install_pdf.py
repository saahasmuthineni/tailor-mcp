"""One-shot: render the Windows demo install instructions to a PDF.

Run via: uv run --with reportlab python scripts/build_demo_install_pdf.py
"""
from __future__ import annotations

from pathlib import Path

from reportlab.lib.colors import HexColor
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    HRFlowable,
    ListFlowable,
    ListItem,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

OUT = Path(__file__).resolve().parent.parent / "Tailor-Windows-Demo-Install.pdf"

styles = getSampleStyleSheet()
INK = HexColor("#1a1a1a")
ACCENT = HexColor("#2c5282")
MUTED = HexColor("#666666")
CODE_BG = HexColor("#f4f4f4")
CALLOUT_BG = HexColor("#fff8e1")

title = ParagraphStyle(
    "title",
    parent=styles["Title"],
    fontSize=22,
    leading=26,
    textColor=ACCENT,
    alignment=TA_LEFT,
    spaceAfter=6,
)
subtitle = ParagraphStyle(
    "subtitle",
    parent=styles["Normal"],
    fontSize=11,
    leading=14,
    textColor=MUTED,
    spaceAfter=18,
)
h2 = ParagraphStyle(
    "h2",
    parent=styles["Heading2"],
    fontSize=15,
    leading=19,
    textColor=ACCENT,
    spaceBefore=14,
    spaceAfter=8,
)
body = ParagraphStyle(
    "body",
    parent=styles["BodyText"],
    fontSize=10.5,
    leading=14.5,
    textColor=INK,
    spaceAfter=8,
)
code = ParagraphStyle(
    "code",
    parent=styles["Code"],
    fontName="Courier",
    fontSize=10,
    leading=13,
    textColor=INK,
    backColor=CODE_BG,
    borderPadding=8,
    leftIndent=0,
    rightIndent=0,
    spaceBefore=4,
    spaceAfter=10,
)
callout = ParagraphStyle(
    "callout",
    parent=body,
    backColor=CALLOUT_BG,
    borderPadding=10,
    borderColor=HexColor("#f0c040"),
    borderWidth=0.5,
    textColor=INK,
)


def p(text: str) -> Paragraph:
    return Paragraph(text, body)


def code_block(text: str) -> Paragraph:
    return Paragraph(text.replace(" ", "&nbsp;"), code)


def bullets(items: list[str]) -> ListFlowable:
    return ListFlowable(
        [ListItem(Paragraph(t, body), leftIndent=12) for t in items],
        bulletType="bullet",
        bulletFontSize=8,
        leftIndent=14,
    )


def numbered(items: list[str]) -> ListFlowable:
    return ListFlowable(
        [ListItem(Paragraph(t, body), leftIndent=14) for t in items],
        bulletType="1",
        bulletFontSize=10,
        leftIndent=18,
    )


story: list = []

story.append(Paragraph("Tailor — Windows Demo Install", title))
story.append(
    Paragraph(
        "About 10 minutes to set up; the demo itself takes 5 minutes. Follow the "
        "steps in order. If anything looks different from what's described below, "
        "take a screenshot and send it before continuing.",
        subtitle,
    )
)
story.append(HRFlowable(width="100%", thickness=0.5, color=MUTED, spaceAfter=12))

story.append(Paragraph("What you'll need", h2))
story.append(
    bullets(
        [
            "A Windows 10 or 11 PC",
            "An internet connection",
            "A free Anthropic account (sign up at "
            "<a href='https://claude.ai' color='#2c5282'>claude.ai</a> if you don't have one)",
            "<b>Claude Desktop installed and signed in</b> — download from "
            "<a href='https://claude.ai/download' color='#2c5282'>claude.ai/download</a>. "
            "Plan ~5 minutes for this <i>before</i> starting the steps below.",
            "About 10 minutes",
        ]
    )
)
story.append(
    p(
        "You will <b>not</b> need: GitHub, a programming background, a Python install, "
        "or any participant data. Step 1's tool (<font face='Courier'>uv</font>) "
        "provisions its own Python interpreter behind the scenes."
    )
)
story.append(
    Paragraph(
        "<b>Heads-up on Claude free tier.</b> The demo runs five prompts back-to-back. "
        "If you're on the free plan and have already been chatting with Claude today, "
        "you may bump into the daily message cap mid-demo. Best to do this in a fresh "
        "sitting and not burn messages on warmup chat first.",
        callout,
    )
)

story.append(Paragraph("Step 1 — Install <font face='Courier'>uv</font> (~2 min)", h2))
story.append(
    p(
        "<font face='Courier'>uv</font> is a small Python tool installer. It bundles "
        "its own Python interpreter, so you do <b>not</b> need Python on PATH."
    )
)
story.append(
    numbered(
        [
            "Open <a href='https://docs.astral.sh/uv/getting-started/installation/' color='#2c5282'>"
            "docs.astral.sh/uv/getting-started/installation/</a> and follow the Windows install "
            "instructions. The page gives a one-line PowerShell command.",
            "<b>Close any open PowerShell windows</b> after <font face='Courier'>uv</font> "
            "finishes installing, then open a fresh one. (PowerShell only picks up the "
            "new <font face='Courier'>uv</font> command after a restart.)",
        ]
    )
)
story.append(p("<b>Verify it worked.</b> In the new PowerShell window, type:"))
story.append(code_block("uv --version"))
story.append(
    p(
        "You should see something like <font face='Courier'>uv 0.4.x</font> (any version is fine). "
        "If you see &quot;not recognized&quot;, close the window and open another fresh one."
    )
)

story.append(Paragraph("Step 2 — Install Tailor (~2 min)", h2))
story.append(p("In the same PowerShell window, type:"))
story.append(code_block("uv tool install tailor-mcp"))
story.append(
    p(
        "You'll see a few &quot;Resolving...&quot; and &quot;Installed...&quot; lines stream past. "
        "When the prompt comes back, the install is done."
    )
)
story.append(p("<b>Verify it worked.</b> Type:"))
story.append(code_block("tailor --help"))
story.append(
    p(
        "You should see a help screen listing subcommands including "
        "<font face='Courier'>serve</font>, <font face='Courier'>pilot</font>, "
        "<font face='Courier'>fitting-room</font>, <font face='Courier'>walkthrough</font>. "
        "If &quot;not recognized&quot;, open a fresh PowerShell window and try again."
    )
)

story.append(Paragraph("Step 3 — Scaffold the demo (~1 min)", h2))
story.append(p("Type:"))
story.append(code_block("tailor fitting-room"))
story.append(p("This single command does everything:"))
story.append(
    bullets(
        [
            "Copies 16 synthetic-participant data files into a working folder",
            "Writes a configuration file",
            "Indexes a small notes database",
            "<b>Adds the demo to Claude Desktop's configuration automatically</b> — "
            "no JSON editing, no copy-pasting paths",
        ]
    )
)
story.append(p("You'll see four progress lines:"))
story.append(
    code_block(
        "  (1/4) copy bundled fixtures<br/>"
        "        force/=17, emg/=17, mrs/=17, vault/=1<br/>"
        "  (2/4) write user_config.json<br/>"
        "  (3/4) index vault.db<br/>"
        "  (4/4) register with Claude Desktop<br/>"
        "        wrote entry 'tailor-fitting-room-cohort' to ..."
    )
)
story.append(
    p(
        "If anything different prints (especially red error text), copy the output "
        "and send it before continuing."
    )
)

story.append(PageBreak())

story.append(Paragraph("Step 4 — Restart Claude Desktop and run the demo", h2))
story.append(
    Paragraph(
        "<b>Critical step most people miss.</b> Find Claude Desktop's icon in the "
        "<b>system tray</b> (near the clock, bottom-right). It may be hidden under the "
        "small up-arrow <font face='Courier'>^</font> — click that to expand the tray. "
        "<b>Right-click the icon → Quit</b>, not just close the window. Closing the "
        "window leaves Claude Desktop running in the background, so reopening it won't "
        "pick up the new demo entry. Then re-open Claude Desktop from the Start menu.",
        callout,
    )
)
story.append(
    p(
        "In a fresh chat, send these prompts <b>one at a time</b>, waiting for each "
        "response before sending the next."
    )
)

story.append(Paragraph("Prompt 1 — confirm tools loaded", h2))
story.append(code_block("List the available Tailor tools."))
story.append(
    p(
        "Claude should list a long set of tool names — <font face='Courier'>force_csv_*</font>, "
        "<font face='Courier'>emg_csv_*</font>, <font face='Courier'>vault_*</font>, "
        "<font face='Courier'>strava_*</font>. If it says &quot;I don't have MCP tools&quot;, "
        "see Troubleshooting on the next page."
    )
)

story.append(Paragraph("Prompt 2 — the cohort summary", h2))
story.append(
    code_block(
        "Summarize peak isometric force across the cohort, grouped by sex.<br/>"
        "Use the force_cohort_summary tool with metric=max."
    )
)
story.append(
    p(
        "Claude calls a tool and gives you average peak forces for the female and male "
        "groups. <b>The point:</b> 96,000 raw samples got reduced to two summary numbers — "
        "none of the raw data left your computer. That's the core value proposition."
    )
)

story.append(Paragraph("Prompt 3 — single-subject force", h2))
story.append(code_block("Run force_summary on S004's trial."))
story.append(p("You'll see peak force and an MVC window mean for participant S004."))

story.append(Paragraph("Prompt 4 — single-subject EMG", h2))
story.append(code_block("Now run emg_envelope_summary on S004's EMG trial."))
story.append(p("You'll get muscle-activity numbers including a fatigue index."))

story.append(Paragraph("Prompt 5 — the cross-session memory moment", h2))
story.append(code_block("Search the vault for any prior notes about subject S004."))
story.append(
    p(
        "Claude finds a saved note &quot;from two weeks ago&quot; flagging the same "
        "elevated EMG amplitude. <b>The point:</b> the framework persists notes across "
        "sessions and re-surfaces them keyed by participant ID. This is what makes it "
        "useful for long-running research projects."
    )
)
story.append(p("<b>That's the demo.</b>"))

story.append(PageBreak())

story.append(Paragraph("Troubleshooting", h2))
trouble = [
    ["What you see", "What to try"],
    [
        "uv --version says 'not recognized'",
        "Close PowerShell entirely, then open a fresh window. uv adds itself to PATH "
        "on install but existing windows don't pick it up until restarted.",
    ],
    [
        "uv tool install fails with a permissions error",
        "Close PowerShell, then re-open as Administrator (right-click PowerShell in the "
        "Start menu → Run as Administrator) and try again.",
    ],
    [
        "tailor --help is 'not recognized'",
        "Open a new PowerShell window so it picks up the new install.",
    ],
    [
        "Claude Desktop doesn't list any Tailor tools",
        "Fully quit Claude Desktop via the system tray (right-click → Quit), then re-open. "
        "If still missing, run 'tailor fitting-room --force' to re-write the Claude Desktop "
        "config and restart again.",
    ],
    [
        "Claude says 'the tool errored' on Prompt 2",
        "Run 'tailor fitting-room --force' to re-scaffold the demo data.",
    ],
    [
        "Vault search (Prompt 5) returns nothing",
        "Same fix — 'tailor fitting-room --force'.",
    ],
    [
        "Anything else",
        "Take a screenshot of the PowerShell window or Claude chat and send it.",
    ],
]
table_data = [[Paragraph(c, body) for c in row] for row in trouble]
t = Table(table_data, colWidths=[2.1 * inch, 4.0 * inch])
t.setStyle(
    TableStyle(
        [
            ("BACKGROUND", (0, 0), (-1, 0), HexColor("#e8eef7")),
            ("TEXTCOLOR", (0, 0), (-1, 0), ACCENT),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("INNERGRID", (0, 0), (-1, -1), 0.25, HexColor("#cccccc")),
            ("BOX", (0, 0), (-1, -1), 0.5, HexColor("#888888")),
            ("LEFTPADDING", (0, 0), (-1, -1), 6),
            ("RIGHTPADDING", (0, 0), (-1, -1), 6),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ]
    )
)
story.append(t)
story.append(Spacer(1, 18))

story.append(Paragraph("When you're done", h2))
story.append(
    p(
        "Nothing runs in the background after you close Claude Desktop — there's no "
        "service to stop. To remove everything later:"
    )
)
story.append(
    numbered(
        [
            "Delete the folder at <font face='Courier'>%USERPROFILE%\\.tailor\\demos\\cohort\\</font> "
            "(paste that path into File Explorer's address bar to find it).",
            "Open <font face='Courier'>%APPDATA%\\Claude\\claude_desktop_config.json</font> in "
            "Notepad and delete the <font face='Courier'>&quot;tailor-fitting-room-cohort&quot;: { ... }</font> "
            "block (and the comma before it, if any).",
            "Optionally: <font face='Courier'>uv tool uninstall tailor-mcp</font>.",
        ]
    )
)

story.append(Spacer(1, 24))
story.append(HRFlowable(width="100%", thickness=0.5, color=MUTED))
story.append(
    Paragraph(
        "<i>Built by your son. Questions about any step — just text me.</i>",
        ParagraphStyle("foot", parent=body, alignment=TA_LEFT, textColor=MUTED, spaceBefore=8),
    )
)


def _draw_footer(canvas, doc):
    canvas.saveState()
    canvas.setFont("Helvetica", 8)
    canvas.setFillColor(MUTED)
    canvas.drawString(0.75 * inch, 0.5 * inch, "Tailor — Windows demo install")
    canvas.drawRightString(
        LETTER[0] - 0.75 * inch, 0.5 * inch, f"Page {doc.page}"
    )
    canvas.restoreState()


doc = SimpleDocTemplate(
    str(OUT),
    pagesize=LETTER,
    leftMargin=0.85 * inch,
    rightMargin=0.85 * inch,
    topMargin=0.75 * inch,
    bottomMargin=0.75 * inch,
    title="Tailor — Windows Demo Install",
    author="Tailor",
)
doc.build(story, onFirstPage=_draw_footer, onLaterPages=_draw_footer)

print(f"Wrote {OUT}")
