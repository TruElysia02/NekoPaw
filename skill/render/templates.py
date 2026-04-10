from __future__ import annotations

from html import escape


def _document_shell(title: str, body_class: str, inner_html: str, width: int, height: int) -> str:
    page_style = f"--page-width:{width}px;--page-height:{height}px;"
    return f"""<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>{escape(title)}</title>
    <style>
      :root {{
        color-scheme: light;
        --paper: #fbfbf6;
        --ink: #111111;
        --muted: #4b4b4b;
        --line: #1a1a1a;
        --soft: #d7d7d2;
        --page-width: 296px;
        --page-height: 128px;
        font-family: "Segoe UI", "Microsoft YaHei", "Noto Sans", sans-serif;
      }}

      * {{
        box-sizing: border-box;
      }}

      html, body {{
        margin: 0;
        padding: 0;
        background:
          linear-gradient(140deg, #d6d6d1, #efefea 38%, #d3d3ce 100%);
        color: var(--ink);
      }}

      body {{
        min-height: 100vh;
        display: grid;
        place-items: center;
        padding: 12px;
      }}

      .np-page {{
        position: relative;
        width: var(--page-width);
        height: var(--page-height);
        overflow: hidden;
        background:
          radial-gradient(circle at top right, rgba(0, 0, 0, 0.06), transparent 28%),
          linear-gradient(180deg, #ffffff, #f5f5ef);
        color: var(--ink);
        box-shadow:
          0 0 0 3px var(--line),
          8px 8px 0 rgba(0, 0, 0, 0.18);
      }}

      .np-page::before {{
        content: "";
        position: absolute;
        inset: 6px;
        border: 1px solid rgba(0, 0, 0, 0.22);
        pointer-events: none;
      }}

      .np-page--markdown {{
        padding: 10px 12px 12px;
      }}

      .np-page--scene {{
        padding: 0;
      }}

      .md-shell {{
        display: grid;
        grid-template-columns: minmax(0, 1fr);
        gap: 8px;
        height: 100%;
      }}

      .md-shell.has-figure {{
        grid-template-columns: minmax(0, 1fr) 92px;
      }}

      .md-copy {{
        min-width: 0;
        display: flex;
        flex-direction: column;
        gap: 6px;
      }}

      .md-kicker {{
        font-size: 8px;
        letter-spacing: 0.24em;
        text-transform: uppercase;
        color: var(--muted);
      }}

      .md-copy h1,
      .md-copy h2,
      .md-copy h3,
      .md-copy p,
      .md-copy ul,
      .md-copy ol,
      .md-copy blockquote {{
        margin: 0;
      }}

      .md-copy h1 {{
        font-size: 18px;
        line-height: 1.02;
        font-weight: 800;
        max-height: 36px;
        overflow: hidden;
      }}

      .md-copy h2 {{
        font-size: 13px;
        line-height: 1.1;
        font-weight: 700;
      }}

      .md-copy h3 {{
        font-size: 10px;
        line-height: 1.15;
        font-weight: 700;
        text-transform: uppercase;
        letter-spacing: 0.08em;
      }}

      .md-copy p,
      .md-copy li,
      .md-copy blockquote {{
        font-size: 10px;
        line-height: 1.24;
      }}

      .md-copy ul,
      .md-copy ol {{
        padding-left: 14px;
        display: grid;
        gap: 2px;
      }}

      .md-copy blockquote {{
        border-left: 3px solid var(--line);
        padding-left: 6px;
        color: var(--muted);
      }}

      .md-copy hr {{
        margin: 0;
        border: 0;
        border-top: 1px solid rgba(0, 0, 0, 0.25);
      }}

      .md-footer {{
        margin-top: auto;
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 8px;
        padding-top: 4px;
        border-top: 1px solid rgba(0, 0, 0, 0.2);
        font-size: 8px;
        letter-spacing: 0.08em;
        text-transform: uppercase;
      }}

      .md-chip {{
        display: inline-flex;
        align-items: center;
        justify-content: center;
        min-height: 18px;
        padding: 0 8px;
        border: 1px solid var(--line);
        background: rgba(0, 0, 0, 0.04);
        font-weight: 700;
      }}

      .md-figure {{
        position: relative;
        min-width: 0;
        display: flex;
        align-items: stretch;
      }}

      .md-figure::after {{
        content: "image";
        position: absolute;
        left: 6px;
        bottom: 6px;
        padding: 1px 4px;
        background: rgba(255, 255, 255, 0.9);
        border: 1px solid var(--line);
        font-size: 7px;
        letter-spacing: 0.12em;
        text-transform: uppercase;
      }}

      .md-figure img {{
        width: 100%;
        height: 100%;
        object-fit: cover;
        border: 2px solid var(--line);
        filter: grayscale(1) contrast(1.05);
      }}

      .scene-canvas {{
        position: relative;
        width: 100%;
        height: 100%;
      }}

      .scene-block {{
        position: absolute;
        overflow: hidden;
      }}

      .scene-block--text {{
        display: flex;
        padding: 4px;
        white-space: pre-wrap;
      }}

      .scene-block--image img {{
        width: 100%;
        height: 100%;
        display: block;
        filter: grayscale(1) contrast(1.06);
      }}

      .scene-role-title {{
        font-size: 18px;
        line-height: 1.02;
        font-weight: 800;
      }}

      .scene-role-subtitle {{
        font-size: 12px;
        line-height: 1.08;
        font-weight: 700;
      }}

      .scene-role-body {{
        font-size: 10px;
        line-height: 1.22;
      }}

      .scene-role-caption {{
        font-size: 8px;
        line-height: 1.1;
        letter-spacing: 0.14em;
        text-transform: uppercase;
        color: var(--muted);
      }}

      .scene-role-badge {{
        font-size: 9px;
        line-height: 1.05;
        letter-spacing: 0.12em;
        text-transform: uppercase;
        font-weight: 800;
      }}

      .scene-align-left {{
        justify-content: flex-start;
        text-align: left;
      }}

      .scene-align-center {{
        justify-content: center;
        text-align: center;
      }}

      .scene-align-right {{
        justify-content: flex-end;
        text-align: right;
      }}

      .scene-valign-top {{
        align-items: flex-start;
      }}

      .scene-valign-middle {{
        align-items: center;
      }}

      .scene-valign-bottom {{
        align-items: flex-end;
      }}

      .scene-frame {{
        border: 2px solid var(--line);
      }}

      .scene-invert {{
        background: var(--line);
        color: #f7f7f3;
      }}
    </style>
  </head>
  <body class="{escape(body_class)}">
    <main class="np-page {escape(body_class)}" style="{page_style}">
      {inner_html}
    </main>
  </body>
</html>
"""


def build_markdown_document(title: str, content_html: str, has_figure: bool, width: int, height: int) -> str:
    figure_class = "has-figure" if has_figure else ""
    inner_html = f"""
      <section class="md-shell {figure_class}">
        {content_html}
      </section>
    """
    return _document_shell(title, "np-page--markdown", inner_html, width, height)


def build_scene_document(title: str, content_html: str, width: int, height: int) -> str:
    inner_html = f"""
      <section class="scene-canvas">
        {content_html}
      </section>
    """
    return _document_shell(title, "np-page--scene", inner_html, width, height)
