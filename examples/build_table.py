"""Generate an example LaTeX table from synthetic data using only Python's standard library."""

from pathlib import Path
from statistics import mean


def build_table(output_dir: Path) -> Path:
    """Write a table fragment and standalone export wrapper; return the wrapper."""
    samples = (
        ("Control", (1.0, 1.2, 1.1)),
        ("Treatment A", (1.6, 1.8, 1.7)),
        ("Treatment B", (2.2, 2.4, 2.3)),
    )
    lines = [
        r"\begin{tabular}{lrrrr}",
        r"\toprule",
        r"Sample & Run 1 & Run 2 & Run 3 & Mean \\",
        r"\midrule",
    ]
    for name, values in samples:
        cells = [name, *(f"{value:.2f}" for value in values), f"{mean(values):.2f}"]
        lines.append(" & ".join(cells) + r" \\")
    lines.extend((r"\bottomrule", r"\end{tabular}"))

    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "example-table.tex").write_text("\n".join(lines) + "\n", encoding="utf-8")
    wrapper = output_dir / "tables" / "example-table.tex"
    wrapper.parent.mkdir(parents=True, exist_ok=True)
    wrapper.write_text(
        "\\documentclass[border=4pt]{standalone}\n"
        "\\input{shared-table-preamble}\n"
        "\\begin{document}\n"
        "\\input{build/examples/example-table.tex}\n"
        "\\end{document}\n",
        encoding="utf-8",
    )
    return wrapper


if __name__ == "__main__":
    build_table(Path(__file__).resolve().parents[1] / "build" / "examples")
