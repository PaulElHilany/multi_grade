"""
Generation of solution-key outputs for MultiGrade.

This module creates the grading-key data used by both the desktop and mobile
grading workflows. It supports:
- assigning exam numbers to one or more key variants,
- shuffling answer-choice order to create anti-cheating variants,
- exporting a human-readable PDF reference,
- exporting a compact TXT format for programmatic use,
- exporting a QR code for mobile import.
"""

import os
import random
from datetime import datetime

import qrcode
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas


def allocate_keys(number_of_exams):
    """
    Randomly assign exam numbers into three groups.

    The three groups correspond to the three available correction-key variants.
    If the total number of exams is not divisible by three, the final group
    receives the remaining exam numbers.

    Parameters:
        number_of_exams (int): Total number of exam sheets.

    Returns:
        tuple[list[int], list[int], list[int]]: Three lists of exam numbers.
    """
    exam_numbers = [i + 1 for i in range(number_of_exams)]
    random.shuffle(exam_numbers)

    third = number_of_exams // 3
    first_set = exam_numbers[:third]
    second_set = exam_numbers[third:2 * third]
    third_set = exam_numbers[2 * third:]

    return first_set, second_set, third_set


def three_solution_keys(solution_grid):
    """
    Build three solution-key variants from the original solution grid.

    The first key keeps the original answer-choice order.
    The second and third keys shuffle the order of answer choices within each
    question while preserving which choices are correct.

    Each answer choice is stored as:
        [numeric_value, letter_label]

    where:
    - numeric_value is 0 or 1,
    - letter_label is the displayed answer choice such as A, B, C, ...

    Parameters:
        solution_grid (list[list[int]]): Original binary solution structure.

    Returns:
        list[list[list[list]]]: Three full key variants.
    """
    alphabet = ["A", "B", "C", "D", "E", "F", "G", "H", "I"]
    key_pairs = []

    for i in range(3):
        version = []

        for row in solution_grid:
            pairs = [[value, alphabet[c]] for c, value in enumerate(row)]

            # Keep the first key unchanged; shuffle the remaining two versions.
            if i != 0:
                random.shuffle(pairs)

            version.append(pairs)

        key_pairs.append(version)

    return key_pairs


def key_type_split(sl_alph_key):
    """
    Split a key variant into numeric and letter-only forms.

    Parameters:
        sl_alph_key (list[list[list]]): A solution key where each answer choice
            is stored as [numeric_value, letter_label].

    Returns:
        tuple[list[list[int]], list[list[str]]]:
            - numeric key containing only 0/1 values
            - alphabetic key containing only displayed choice letters
    """
    sl_key = [[pair[0] for pair in row] for row in sl_alph_key]
    alph_key = [[pair[1] for pair in row] for row in sl_alph_key]
    return sl_key, alph_key


def format_pair_list_for_pdf(row):
    """
    Convert one question row into a printable PDF string.

    Example:
        [[1, 'A'], [0, 'B'], [1, 'C']]
    becomes:
        "(1)A   (0)B   (1)C"

    Parameters:
        row (list[list]): One question row of [value, letter] pairs.

    Returns:
        str: Formatted text suitable for the PDF reference output.
    """
    return "   ".join(f"({value}){letter}" for value, letter in row)


def print_keys(number_of_exams, solution_grid, same_key_for_all=False):
    """
    Build both PDF-oriented and machine-readable key outputs.

    Two output structures are produced:
    - pdf_output: a human-readable structure used to generate the reference PDF
    - key_for_python: a compact structure used to generate the TXT/QR data

    Parameters:
        number_of_exams (int): Number of exam sheets to assign keys to.
        solution_grid (list[list[int]]): Original binary solution structure.
        same_key_for_all (bool, optional): If True, all exam numbers use the
            same key variant. If False, exam numbers are split across three
            key variants.

    Returns:
        tuple[dict, dict]:
            - pdf_output for PDF generation
            - key_for_python for TXT/QR export
    """
    sl_alph_keys = three_solution_keys(solution_grid)

    three_sets = allocate_keys(number_of_exams)
    generated_on = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    if same_key_for_all:
        common_key = sl_alph_keys[0]
        common_numeric_key = key_type_split(common_key)[0]

        pdf_output = {
            "generated_on": generated_on,
            "sections": [
                {
                    "exam_numbers": sorted([i + 1 for i in range(number_of_exams)]),
                    "key": [format_pair_list_for_pdf(row) for row in common_key],
                }
            ],
        }

        key_for_python = {
            "generated_on": generated_on,
            "keys": [
                [
                    sorted([i + 1 for i in range(number_of_exams)]),
                    common_numeric_key,
                ]
            ],
        }

    else:
        main_key = sl_alph_keys[0]
        first_random_key = sl_alph_keys[1]
        second_random_key = sl_alph_keys[2]

        pdf_output = {
            "generated_on": generated_on,
            "sections": [
                {
                    "exam_numbers": three_sets[0],
                    "key": [format_pair_list_for_pdf(row) for row in main_key],
                },
                {
                    "exam_numbers": three_sets[1],
                    "key": [format_pair_list_for_pdf(row) for row in first_random_key],
                },
                {
                    "exam_numbers": three_sets[2],
                    "key": [format_pair_list_for_pdf(row) for row in second_random_key],
                },
            ],
        }

        # Extract numeric-only keys for machine-readable export.
        s_keys = [key_type_split(sl_alph_keys[i])[0] for i in range(3)]

        key_for_python = {
            "generated_on": generated_on,
            "keys": [[three_sets[i], s_keys[i]] for i in range(3)],
        }

    return pdf_output, key_for_python


def bit_row_to_compact_string(row):
    """
    Convert a list of bits into a compact string.

    Example:
        [1, 0, 1, 1] -> "1011"

    Parameters:
        row (list[int]): List of 0/1 values.

    Returns:
        str: Concatenated bit string.
    """
    return "".join(str(v) for v in row)


def compact_key_row_to_string(key_row):
    """
    Convert one machine-readable key row into the custom compact TXT format.

    Expected input:
        [exam_numbers, answer_rows]

    Example input:
        [[2], [[1,1,1], [1,0], [1,1,0,1]]]

    Example output:
        [[2], 111, 10, 1101]

    Parameters:
        key_row (list): One entry of the internal key-export structure.

    Returns:
        str: Compact text representation of that row.
    """
    exam_numbers, answer_rows = key_row
    compact_parts = [repr(exam_numbers)] + [bit_row_to_compact_string(row) for row in answer_rows]
    return "[" + ", ".join(compact_parts) + "]"


def keys_txt_string(txt_data):
    """
    Convert machine-readable key data into the project's compact TXT format.

    Example output:
        {'g': '2026-04-08 13:17:19', 'k':
        [[2], 111, 10, 1101],
        [[3], 010, 10, 1101]
        }

    This text format is used both for saved TXT files and as the QR-code payload.

    Parameters:
        txt_data (dict): Dictionary containing generation time and key rows.

    Returns:
        str: Full compact TXT representation.
    """
    generated_on = txt_data["generated_on"]
    key_rows = txt_data["keys"]

    row_strings = [compact_key_row_to_string(row) for row in key_rows]

    return "{'g': " + repr(generated_on) + ", 'k':\n" + ",\n".join(row_strings) + "\n}"


def save_keys_txt(txt_data, filename="sol_keys.txt"):
    """
    Save the compact key representation to a TXT file.

    Parameters:
        txt_data (dict): Machine-readable key data.
        filename (str, optional): Output TXT filename.

    Returns:
        str: The saved filename.
    """
    txt_string = keys_txt_string(txt_data)

    with open(filename, "w", encoding="utf-8") as f:
        f.write(txt_string)

    return filename


def save_keys_pdf(pdf_data, filename="sol_keys_ref.pdf"):
    """
    Save the human-readable reference key as a PDF file.

    The PDF groups exam numbers by assigned key variant and prints each
    question's answer-choice mapping in a compact readable form.

    Parameters:
        pdf_data (dict): Structured PDF content returned by print_keys().
        filename (str, optional): Output PDF filename.

    Returns:
        str: The saved filename.
    """
    c = canvas.Canvas(filename, pagesize=A4)
    width, height = A4

    title_font_size = 10
    body_font_size = 7

    left_margin = 50
    top_margin = height - 50
    line_height = 11

    y = top_margin

    def new_page():
        """
        Start a new PDF page and reset the current vertical cursor position.
        """
        nonlocal y
        c.showPage()
        y = top_margin
        c.setFont("Helvetica", body_font_size)

    c.setFont("Helvetica-Bold", title_font_size)
    c.drawString(left_margin, y, "User Solution Key (for Reference)")
    y -= line_height * 1.5

    c.setFont("Helvetica", body_font_size)
    c.drawString(left_margin, y, f"Generated on: {pdf_data['generated_on']}")
    y -= line_height * 2

    for idx, section in enumerate(pdf_data["sections"], start=1):
        header = f"Item {idx}: Numbers in {section['exam_numbers']} have the solution key:"
        c.setFont("Helvetica-Bold", body_font_size)
        c.drawString(left_margin, y, header)
        y -= line_height

        c.setFont("Helvetica", body_font_size)

        for row_number, row_text in enumerate(section["key"], start=1):
            line = f"Q{row_number}: {row_text}"

            if y < 50:
                new_page()

            c.drawString(left_margin + 10, y, line)
            y -= line_height

        y -= line_height

        if y < 50:
            new_page()

    c.save()
    return filename


def save_keys_qr(txt_string, filename="sol_keys_qr.png"):
    """
    Encode the compact TXT key data into a QR code image.

    Parameters:
        txt_string (str): Compact key text to store inside the QR code.
        filename (str, optional): Output image filename.

    Returns:
        str: The saved filename.

    Raises:
        ValueError: If the content is too large to fit into a single QR code.
    """
    try:
        qr = qrcode.QRCode(
            version=None,
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            box_size=10,
            border=4,
        )
        qr.add_data(txt_string)
        qr.make(fit=True)

        img = qr.make_image(fill_color="black", back_color="white")
        img.save(filename)
        return filename

    except Exception as e:
        raise ValueError(
            "The generated TXT content is too large to fit into a single QR code."
        ) from e


def save_print_keys_outputs(
    number_of_exams,
    solution_grid,
    output_dir=".",
    timestamp=None,
    same_key_for_all=False,
):
    """
    Generate and save all solution-key output files.

    This convenience function creates:
    - a human-readable PDF reference,
    - a compact TXT key file,
    - a QR-code image containing the compact TXT payload.

    Parameters:
        number_of_exams (int): Number of exam sheets.
        solution_grid (list[list[int]]): Original binary solution structure.
        output_dir (str, optional): Destination directory for generated files.
        timestamp (str, optional): Timestamp string used in filenames.
            If None, a timestamp is generated automatically.
        same_key_for_all (bool, optional): If True, assign one key to all tests.

    Returns:
        tuple[str, str, str]:
            - path to the generated PDF
            - path to the generated TXT file
            - path to the generated QR image
    """
    if timestamp is None:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    os.makedirs(output_dir, exist_ok=True)

    pdf_data, txt_data = print_keys(
        number_of_exams,
        solution_grid,
        same_key_for_all=same_key_for_all,
    )
    txt_string = keys_txt_string(txt_data)

    pdf_path = save_keys_pdf(
        pdf_data,
        filename=os.path.join(output_dir, f"sol_keys_ref_{timestamp}.pdf"),
    )
    txt_path = save_keys_txt(
        txt_data,
        filename=os.path.join(output_dir, f"sol_keys_{timestamp}.txt"),
    )
    qr_path = save_keys_qr(
        txt_string,
        filename=os.path.join(output_dir, f"sol_keys_qr_{timestamp}.png"),
    )

    return pdf_path, txt_path, qr_path
