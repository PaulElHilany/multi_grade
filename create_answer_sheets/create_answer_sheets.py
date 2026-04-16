"""
LaTeX/PDF generation for numbered answer sheets.

This module builds a LaTeX document containing one or more answer sheets and
compiles it into a PDF using pdflatex. The geometric layout and drawing helpers
are imported from create_answer_sheets_functions.
"""

import os
import subprocess
from datetime import datetime

from create_answer_sheets_functions import (
    define_marker_anchors,
    define_annotation_anchors,
    define_answer_anchors,
    invert,
    anchor_to_roi,
    anchor_to_square,
    anchor_to_question,
    anchor_to_choice,
    create_symbols,
    preamble,
    common_part_begin,
    common_part_end,
    end_document,
    new_page,
)


def exams_latex(sltns, number_of_sheets):
    """
    Build the LaTeX source for a set of numbered answer sheets.

    Each generated page corresponds to one answer sheet. The page layout is
    determined by the number of answer choices for each question, inferred from
    the provided solutions structure.

    Parameters:
        sltns (list[list[int]]): Solution structure where each inner list
            represents one question and its available answer choices.
        number_of_sheets (int): Number of numbered answer-sheet pages to generate.

    Returns:
        str: Complete LaTeX document as a string.
    """
    # The number of answer boxes per question determines the grid layout.
    grid_structure = [len(sol) for sol in sltns]
    latex_content = preamble

    for i in range(number_of_sheets):
        latex_content += (
            common_part_begin
            + create_symbols(grid_structure, i + 1)
            + common_part_end
        )
        latex_content += new_page if i != number_of_sheets - 1 else end_document

    return latex_content


def exams_pdf(
    sltns,
    number_of_sheets,
    output_dir=".",
    timestamp=None,
    pdflatex_path="pdflatex",
):
    """
    Generate a PDF file containing numbered answer sheets.

    This function writes a temporary LaTeX file, compiles it with pdflatex, and
    returns the path to the generated PDF. Temporary LaTeX build files are removed
    afterwards.

    Parameters:
        sltns (list[list[int]]): Solution structure describing the number of
            answer choices for each question.
        number_of_sheets (int): Number of answer sheets to generate.
        output_dir (str, optional): Directory where the PDF should be written.
            Defaults to the current directory.
        timestamp (str, optional): Timestamp string used in the output filename.
            If None, a timestamp is generated automatically.
        pdflatex_path (str, optional): Path to the pdflatex executable, or the
            command name if it is available on PATH.

    Returns:
        str: Full path to the generated PDF file.

    Raises:
        FileNotFoundError: If pdflatex cannot be found.
        RuntimeError: If LaTeX compilation fails.
    """
    if timestamp is None:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    os.makedirs(output_dir, exist_ok=True)

    tex_file = f"tests_{timestamp}.tex"
    pdf_file = f"tests_{timestamp}.pdf"
    aux_file = f"tests_{timestamp}.aux"
    log_file = f"tests_{timestamp}.log"

    tex_path = os.path.join(output_dir, tex_file)
    pdf_path = os.path.join(output_dir, pdf_file)
    aux_path = os.path.join(output_dir, aux_file)
    log_path = os.path.join(output_dir, log_file)

    # Write the LaTeX source for the requested answer sheets.
    with open(tex_path, "w", encoding="utf-8") as f:
        f.write(exams_latex(sltns, number_of_sheets))

    try:
        # Compile the LaTeX file inside the output directory so all build files
        # are created there rather than in the working directory of the caller.
        subprocess.run(
            [pdflatex_path, "-interaction=nonstopmode", "-halt-on-error", tex_file],
            check=True,
            shell=False,
            cwd=output_dir,
        )

    except FileNotFoundError:
        raise FileNotFoundError(
            "pdflatex was not found. On Windows, install MiKTeX or TeX Live "
            "and either add pdflatex to PATH or pass its full path via pdflatex_path."
        )

    except subprocess.CalledProcessError as e:
        raise RuntimeError(
            f"LaTeX compilation failed for {tex_path}. Check the generated .log file for details."
        ) from e

    finally:
        # Keep the final PDF, but remove temporary LaTeX build files.
        for temp_file in [tex_path, aux_path, log_path]:
            if os.path.exists(temp_file):
                os.remove(temp_file)

    return pdf_path
