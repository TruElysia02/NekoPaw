from __future__ import annotations

from html import escape


def _theme_style(theme: dict[str, str] | None) -> str:
    if not theme:
        return ""
    return "".join(f"{name}:{value};" for name, value in theme.items())


def _document_shell(
    title: str,
    body_class: str,
    inner_html: str,
    width: int,
    height: int,
    *,
    theme: dict[str, str] | None = None,
) -> str:
    page_style = f"--page-width:{width}px;--page-height:{height}px;{_theme_style(theme)}"
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
        --frame-stroke: 2px;
        --md-kicker-size: 8px;
        --md-kicker-letter: 0.24em;
        --md-kicker-transform: uppercase;
        --md-title-size: 18px;
        --md-subtitle-size: 13px;
        --md-heading-size: 10px;
        --md-heading-letter: 0.08em;
        --md-heading-transform: uppercase;
        --md-body-size: 10px;
        --md-body-line: 1.24;
        --md-footer-size: 8px;
        --md-footer-letter: 0.08em;
        --md-chip-size: 9px;
        --scene-title-size: 18px;
        --scene-subtitle-size: 12px;
        --scene-body-size: 10px;
        --scene-body-line: 1.22;
        --scene-caption-size: 8px;
        --scene-caption-letter: 0.14em;
        --scene-caption-transform: uppercase;
        --scene-badge-size: 9px;
        --scene-badge-letter: 0.12em;
        --scene-badge-transform: uppercase;
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
        font-size: var(--md-kicker-size);
        letter-spacing: var(--md-kicker-letter);
        text-transform: var(--md-kicker-transform);
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
        font-size: var(--md-title-size);
        line-height: 1.02;
        font-weight: 800;
        max-height: 36px;
        overflow: hidden;
      }}

      .md-copy h2 {{
        font-size: var(--md-subtitle-size);
        line-height: 1.1;
        font-weight: 700;
      }}

      .md-copy h3 {{
        font-size: var(--md-heading-size);
        line-height: 1.15;
        font-weight: 700;
        text-transform: var(--md-heading-transform);
        letter-spacing: var(--md-heading-letter);
      }}

      .md-copy p,
      .md-copy li,
      .md-copy blockquote {{
        font-size: var(--md-body-size);
        line-height: var(--md-body-line);
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
        font-size: var(--md-footer-size);
        letter-spacing: var(--md-footer-letter);
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
        font-size: var(--md-chip-size);
      }}

      .md-figure {{
        position: relative;
        min-width: 0;
        display: flex;
        align-items: stretch;
      }}

      .md-figure-frame {{
        position: relative;
        width: 100%;
        height: 100%;
      }}

      .md-figure-label {{
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

      .md-figure-frame img {{
        width: 100%;
        height: 100%;
        object-fit: cover;
        filter: grayscale(1) contrast(1.05);
      }}

      .md-figure-frame::after {{
        content: "";
        position: absolute;
        inset: 0;
        border: var(--frame-stroke) solid var(--line);
        pointer-events: none;
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
        overflow-wrap: anywhere;
      }}

      .scene-block--image {{
        margin: 0;
      }}

      .scene-block--image-frame {{
        position: absolute;
        inset: 0;
        border: var(--frame-stroke) solid var(--line);
        pointer-events: none;
        background: transparent;
      }}

      .scene-block--image img {{
        width: 100%;
        height: 100%;
        display: block;
        filter: grayscale(1) contrast(1.06);
      }}

      .scene-role-title {{
        font-size: var(--scene-title-size);
        line-height: 1.02;
        font-weight: 800;
      }}

      .scene-role-subtitle {{
        font-size: var(--scene-subtitle-size);
        line-height: 1.08;
        font-weight: 700;
      }}

      .scene-role-body {{
        font-size: var(--scene-body-size);
        line-height: var(--scene-body-line);
      }}

      .scene-role-caption {{
        font-size: var(--scene-caption-size);
        line-height: 1.1;
        letter-spacing: var(--scene-caption-letter);
        text-transform: var(--scene-caption-transform);
        color: var(--muted);
      }}

      .scene-role-badge {{
        font-size: var(--scene-badge-size);
        line-height: 1.05;
        letter-spacing: var(--scene-badge-letter);
        text-transform: var(--scene-badge-transform);
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
        border: var(--frame-stroke) solid var(--line);
      }}

      .scene-invert {{
        background: var(--line);
        color: #f7f7f3;
      }}

      body[data-np-capture="image"] .np-page,
      body[data-np-capture="foreground"] .np-page {{
        background: #ffffff;
        box-shadow: none;
      }}

      body[data-np-capture="image"] .np-page::before,
      body[data-np-capture="foreground"] .np-page::before {{
        display: none;
      }}

      body[data-np-capture="image"] [data-np-layer="foreground"] {{
        visibility: hidden !important;
      }}

      body[data-np-capture="foreground"] [data-np-layer="image"] {{
        visibility: hidden !important;
      }}

      body[data-np-capture="foreground"] .scene-block--image img,
      body[data-np-capture="foreground"] .md-figure-frame img {{
        filter: none !important;
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


def build_markdown_document(
    title: str,
    content_html: str,
    has_figure: bool,
    width: int,
    height: int,
    *,
    theme: dict[str, str] | None = None,
) -> str:
    figure_class = "has-figure" if has_figure else ""
    inner_html = f"""
      <section class="md-shell {figure_class}">
        {content_html}
      </section>
    """
    return _document_shell(title, "np-page--markdown", inner_html, width, height, theme=theme)


def build_scene_document(
    title: str,
    content_html: str,
    width: int,
    height: int,
    *,
    theme: dict[str, str] | None = None,
) -> str:
    inner_html = f"""
      <section class="scene-canvas">
        {content_html}
      </section>
    """
    return _document_shell(title, "np-page--scene", inner_html, width, height, theme=theme)
