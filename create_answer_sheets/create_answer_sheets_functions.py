"""
Helper functions and LaTeX/TikZ fragments for answer-sheet generation.

This module defines the geometric anchor positions used to draw answer sheets,
along with helper functions that convert those anchors into TikZ code.

It also provides the shared LaTeX fragments used by create_answer_sheets.py to
build the final answer-sheet PDF.
"""


def define_marker_anchors(h_markers_number, w_markers_number):
    """
    Build the anchor positions for the black marker squares.

    Height markers are placed along the left and right sheet borders.
    Width markers are placed along the top and bottom sheet borders.

    Parameters:
        h_markers_number (int): Number of vertical marker positions.
        w_markers_number (int): Number of horizontal marker positions.

    Returns:
        tuple[list[tuple[int, int]], list[tuple[int, int]]]:
            - height marker anchors
            - width marker anchors
    """
    h_markers = [
        marker
        for h in range(h_markers_number)
        for marker in ((128 + 24 * h, 60), (128 + 24 * h, 684))
    ]

    w_markers = [
        marker
        for w in range(w_markers_number)
        for marker in ((16, 172 + 64 * w), (848, 172 + 64 * w))
    ]

    return h_markers, w_markers


def define_annotation_anchors(h_markers_number, w_markers_number):
    """
    Build the anchor positions used for question labels and choice labels.

    Parameters:
        h_markers_number (int): Number of question rows.
        w_markers_number (int): Maximum number of answer choices across questions.

    Returns:
        tuple[list[list[tuple[float, float]]], list[list[tuple[int, int]]]]:
            - question anchors: reserved question-area anchor and text position
            - choice anchors: rectangle position and label position for each choice
    """
    question_anchors = [
        [(139.5 + 24 * h, 127.5), (126 + 24 * h, 122)]
        for h in range(h_markers_number)
    ]

    choice_anchors = [
        [(63, 171 + 64 * w), (67, 174 + 64 * w)]
        for w in range(w_markers_number)
    ]

    return question_anchors, choice_anchors


def define_answer_anchors(grid_structure):
    """
    Build the anchor positions of all answer boxes from the grid structure.

    Each entry in grid_structure gives the number of choices for one question.

    Parameters:
        grid_structure (list[int]): Number of answer choices for each question.

    Returns:
        list[tuple[int, int]]: Anchor positions for all answer boxes.
    """
    answer_anchors = []

    for i in range(len(grid_structure)):
        for c in range(grid_structure[i]):
            answer_anchors.append((128 + 24 * i, 172 + 64 * c))

    return answer_anchors


def invert(vector):
    """
    Reverse the coordinate order of a point/vector.

    This helper is used because anchor positions are stored in one coordinate
    order while TikZ expects coordinates in (x, y) order.

    Parameters:
        vector (tuple): Input coordinate tuple.

    Returns:
        tuple: Reversed coordinate tuple.
    """
    return tuple(reversed(vector))


def anchor_to_roi(vector, number):
    """
    Convert an anchor position into TikZ code for the test-number label.

    Parameters:
        vector (tuple[int, int]): Anchor position of the ROI label area.
        number (int): Test number to display.

    Returns:
        str: TikZ code that places the test number text.
    """
    invector = invert(vector)
    invector_2 = (invector[0] + 16, invector[1] + 8)

    # Place the test number near the ROI anchor.
    return (
        f"\n\\draw {invector_2} node [anchor=north west][inner sep=0.75pt]   "
        f"[align=left][font=\\Huge]"
        + r"{\textbf{\texttt{"
        + f"{number}"
        + r"}}}"
        + ";\n"
    )


def anchor_to_square(vector, type, ratio):
    """
    Convert an anchor position into TikZ code for a square or rectangular box.

    Parameters:
        vector (tuple[int, int]): Anchor position.
        type (int): Fill type:
            - 0 -> white square
            - 1 -> black square
        ratio (int): Height ratio:
            - 1 -> square
            - 2 -> rectangle

    Returns:
        str: TikZ code for the requested shape.
    """
    invector = invert(vector)
    color = "255; green, 255; blue, 255" if type == 0 else "0; green, 0; blue, 0"
    label = "white" if type == 0 else "black"

    return (
        f"% {label} square at {invector}:\n\\draw  "
        f"[fill={{rgb, 255:red, {color} }}  ,fill opacity=1 ] "
        f"{invector} -- {(invector[0] + 16, invector[1])} -- {(invector[0] + 16, invector[1] + 16 // ratio)} -- "
        f"{(invector[0], invector[1] + 16 // ratio)} -- cycle ;\n"
    )


def anchor_to_question(nvector, number):
    """
    Convert a question-number text anchor into TikZ code.

    Parameters:
        nvector (tuple[int, int]): Question-number text anchor position.
        number (int): Question number.

    Returns:
        str: TikZ code placing the question number text.
    """
    return (
        f"\\draw {invert(nvector)} node [anchor=north west][inner sep=0.75pt] "
        f"[align=left] {{{number}\ --}};\n"
    )


def anchor_to_choice(sqr_vector, l_vector, letter):
    """
    Convert choice anchors into TikZ code for the choice rectangle and label.

    Parameters:
        sqr_vector (tuple[int, int]): Anchor for the outer choice rectangle.
        l_vector (tuple[int, int]): Anchor for the displayed answer-choice letter.
        letter (str): Choice label, such as 'a', 'b', 'c', ...

    Returns:
        str: TikZ code for the rectangle and its letter label.
    """
    anchor_1 = invert(sqr_vector)
    anchor_2 = invert(l_vector)

    return (
        f"% choice number {letter} at {sqr_vector}:\n"
        f"\\draw    {anchor_1} -- "
        f"{(anchor_1[0] + 17, anchor_1[1])} -- {(anchor_1[0] + 17, anchor_1[1] + 25)} -- "
        f"{(anchor_1[0], anchor_1[1] + 25)} -- cycle;\n"
        f"\\draw {anchor_2} node [anchor=north west][inner sep=0.75pt]   "
        f"[align=left] {{ {letter} }};\n"
    )


def create_symbols(grid_structure, test_number):
    """
    Generate all TikZ symbols needed for one answer sheet.

    This includes:
    - the test number label,
    - black border markers,
    - question number annotations,
    - choice label annotations,
    - white answer boxes.

    Parameters:
        grid_structure (list[int]): Number of answer choices for each question.
        test_number (int): Number to print on the generated answer sheet.

    Returns:
        str: Combined TikZ code for the answer sheet, or an error message if the
        grid exceeds the supported layout size.
    """
    h_markers_number = len(grid_structure)
    w_markers_number = max(grid_structure)

    # Prevent generating a grid larger than the fixed layout supports.
    if h_markers_number > 30 or w_markers_number > 8:
        return "grid is too large"

    marker_anchors = define_marker_anchors(h_markers_number, w_markers_number)
    q_annotation_anchors, c_annotation_anchors = define_annotation_anchors(
        h_markers_number, w_markers_number
    )
    answer_anchors = define_answer_anchors(grid_structure)

    alphabet = ["a", "b", "c", "d", "e", "f", "g", "h"]

    all_symbols = [
        anchor_to_roi((-60, 330), test_number),
        "\n\n",
        "".join(anchor_to_square(anchor, 1, 2) for anchor in marker_anchors[0]),
        "\n\n",
        "".join(anchor_to_square(anchor, 1, 1) for anchor in marker_anchors[1]),
        "\n\n",
        "".join(
            anchor_to_question(number_anchor, i + 1)
            for i, (_, number_anchor) in enumerate(q_annotation_anchors)
        ),
        "\n\n",
        "".join(
            anchor_to_choice(square_anchor, letter_anchor, alphabet[i])
            for i, (square_anchor, letter_anchor) in enumerate(c_annotation_anchors)
        ),
        "\n\n",
        "".join(anchor_to_square(anchor, 0, 2) for anchor in answer_anchors),
        "\n\n",
    ]

    return "".join(all_symbols)


# LaTeX document preamble used to generate the answer-sheet PDF.
preamble = (
    "\\documentclass[11pt]{amsart}\n"
    "\\usepackage{tikz-cd}\n"
    "\\usepackage{atbegshi}% removes the first blank page\n"
    "\\AtBeginDocument{\\AtBeginShipoutNext{\\AtBeginShipoutDiscard}}\n"
    "\n"
    "\\begin{document}\n"
    "\\pagenumbering{gobble}\n"
    "\n"
)


# Beginning of the common TikZ drawing shared by all generated sheets.
# This contains the fixed reference squares used for alignment and calibration.
common_part_begin = (
    "\n"
    "\\vspace*{-2.5cm}\n"
    "\\hspace*{-2.5cm}\\begin{tikzpicture}[x=0.75pt,y=0.75pt,yscale=-1,xscale=1]\n"
    "\n"
    "\n"
    "\n"
    "% ------------------------ begin of common part --------------------\n"
    "\n"
    "% black reference square:\n"
    "\\draw  [fill={rgb, 255:red, 0; green, 0; blue, 0 }  ,fill opacity=1 ]\n"
    "(732, 432) -- (764+32 , 432) -- (764+32, 432 -36) -- (732, 432- 36) -- cycle ;\n"
    "\n"
    "% NW square at (60, 16):\n"
    "\\draw  [fill={rgb, 255:red, 0; green, 0; blue, 0 }  ,fill opacity=1 ]"
    "         (60, 16) -- (76, 16) -- (76, 32) --         (60, 32) -- cycle ;\n"
    "\n"
    "% SW square at (60, 848):\n"
    "\\draw  [fill={rgb, 255:red, 0; green, 0; blue, 0 }  ,fill opacity=1 ]"
    "         (60, 848) -- (76, 848) -- (76, 864) --         (60, 864) -- cycle ;\n"
    "\n"
    "% NE square at (684, 16):\n"
    "\\draw  [fill={rgb, 255:red, 0; green, 0; blue, 0 }  ,fill opacity=1 ]"
    "         (684, 16) -- (700, 16) -- (700, 32) --         (684, 32) -- cycle ;\n"
    "\n"
    "% SE square at (684, 848):\n"
    "\\draw  [fill={rgb, 255:red, 0; green, 0; blue, 0 }  ,fill opacity=1 ]"
    "         (684, 848) -- (700, 848) -- (700, 864) --         (684, 864) -- cycle ;\n"
    "\n"
    "%----------------------------- end of common part ------------------\n"
)


# End of the shared TikZ picture block.
common_part_end = "\n\n\\end{tikzpicture}\n\n"

# End of the LaTeX document.
end_document = "\n\n\\end{document}\n"

# LaTeX command used to insert a page break between generated sheets.
new_page = "\n\n\\newpage\n"
