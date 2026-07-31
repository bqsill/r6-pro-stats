"""Plain-text table rendering."""


def fmt(value, spec):
    if value is None:
        return "-"
    if spec == "s":
        return str(value)
    return format(value, spec)


def render(rows, columns) -> str:
    """columns: list of (key, header, format_spec). Numeric specs right-align."""
    table = []
    for row in rows:
        get = row.get if isinstance(row, dict) else (lambda k, r=row: r[k])
        table.append([fmt(get(key), spec) for key, _, spec in columns])
    headers = [h for _, h, _ in columns]
    widths = [max(len(h), *(len(r[i]) for r in table)) if table else len(h)
              for i, h in enumerate(headers)]
    aligns = ["<" if spec == "s" else ">" for _, _, spec in columns]

    def line(cells):
        return "  ".join(f"{c:{a}{w}}" for c, a, w in zip(cells, aligns, widths)).rstrip()

    out = [line(headers), line(["-" * w for w in widths])]
    out.extend(line(r) for r in table)
    return "\n".join(out)
