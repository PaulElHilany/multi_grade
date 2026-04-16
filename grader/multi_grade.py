"""
Core grading utilities for batch processing of answer sheets.

This module provides:
- input loading from PDF or image files,
- parsing and normalization of solution-key formats,
- helper functions for recovering loosely formatted key data,
- answer-sheet reading and detailed detection extraction,
- grade computation for batch and single-image workflows.

It relies on image-analysis and pattern-extraction modules for detecting answer
regions and on correction functions for computing grades.
"""

import json
import os
import ast
import re

# Numerical array handling.
import numpy as np

# PDF-to-image conversion utilities.
import pdf2image
from pdf2image import convert_from_path

# OpenCV for image preprocessing.
import cv2 as cv

# Import shared threshold, vector, and image-analysis utilities.
from image_analyzing_functions import (
    light_dark_threshold,
    current_grey_threshold,
    current_color_threshold,
    vector_size,
    norm_vector,
    ImageAnalyzer,
)

# Import functions used to detect markers and extract the answer grid.
from pattern_extraction_functions import (
    gr_and_color_of_dark,
    cone_sweeper,
    locate_corners,
    leading_direction,
    directional_sweeper,
    locate_marker_pairs,
    intersect_lines,
    read_answer_grid,
)

# Import grading utilities.
from answer_correction_functions import (
    answer_list_compare,
    answer_list_grade,
    total_grade,
    total_grade_single,
    total_grade_all,
)


def load_input_pages(file_path):
    """
    Load grading input as a list of pages/images.

    Supported inputs:
    - PDF files, converted into page images
    - single image files (.jpeg, .jpg, .png)

    Parameters:
        file_path (str): Path to the input PDF or image file.

    Returns:
        list: A list of page images. For PDFs, one image per page is returned.
            For a single image input, the returned list contains one image.

    Raises:
        ValueError: If the file cannot be read or the format is unsupported.
    """
    ext = os.path.splitext(file_path)[1].lower()

    if ext == ".pdf":
        return convert_from_path(file_path)

    if ext in [".jpeg", ".jpg", ".png"]:
        img = cv.imread(file_path)
        if img is None:
            raise ValueError(f"Could not read image file: {file_path}")

        # OpenCV loads in BGR order; convert to RGB for downstream consistency.
        img = cv.cvtColor(img, cv.COLOR_BGR2RGB)
        return [img]

    raise ValueError(
        "Unsupported input format. Supported formats are: .pdf, .jpeg, .jpg, .png"
    )


def normalize_answer_pattern(value):
    """
    Normalize one answer-pattern representation into a list of 0/1 integers.

    Supported input types:
    - list of 0/1 values
    - integer composed only of digits 0 and 1
    - string composed only of characters 0 and 1

    Examples:
        [1, 0, 1]
        101
        "101"

    Parameters:
        value: Input answer-pattern representation.

    Returns:
        list[int]: Normalized list of 0/1 integers.

    Raises:
        ValueError: If the value format is unsupported or contains invalid digits.
    """
    if isinstance(value, list):
        result = []
        for i, item in enumerate(value):
            if item not in (0, 1):
                raise ValueError(
                    f"Invalid value {item} in answer pattern list at index {i}. "
                    "Only 0 and 1 are allowed."
                )
            result.append(int(item))
        return result

    if isinstance(value, int):
        text = str(value)
        if any(ch not in "01" for ch in text):
            raise ValueError(
                f"Invalid integer answer pattern {value}. "
                "Only digits 0 and 1 are allowed."
            )
        return [int(ch) for ch in text]

    if isinstance(value, str):
        text = value.strip()
        if any(ch not in "01" for ch in text):
            raise ValueError(
                f"Invalid string answer pattern '{value}'. "
                "Only characters 0 and 1 are allowed."
            )
        return [int(ch) for ch in text]

    raise ValueError(
        f"Unsupported answer pattern format: {value!r}. "
        "Expected a list, int, or string."
    )


def normalize_solution_entry(entry):
    """
    Normalize one solution-key entry into the internal standard form.

    Expected normalized output:
        [exam_numbers, answer_rows]

    where:
    - exam_numbers is a list of integers
    - answer_rows is a list of normalized answer patterns

    The input may already contain the answer rows grouped as one list, or may
    contain them as multiple trailing items.

    Parameters:
        entry (list): One raw solution-key entry.

    Returns:
        list: Normalized solution-key entry.

    Raises:
        ValueError: If the structure is invalid.
    """
    if not isinstance(entry, list):
        raise ValueError(f"Each key entry must be a list, got: {type(entry).__name__}")

    if len(entry) < 2:
        raise ValueError("Each key entry must contain exam numbers and at least one solution.")

    exam_numbers = entry[0]
    if not isinstance(exam_numbers, list):
        raise ValueError("The first item of each key entry must be a list of exam numbers.")

    for i, num in enumerate(exam_numbers):
        if not isinstance(num, int):
            raise ValueError(
                f"Invalid exam number at position {i}: {num}. Exam numbers must be integers."
            )

    # Handle the case where all answer rows are already grouped into one list.
    if len(entry) == 2 and isinstance(entry[1], list):
        second = entry[1]
        if all(isinstance(x, (list, str, int)) for x in second):
            return [exam_numbers, [normalize_answer_pattern(x) for x in second]]

    # Otherwise, treat all trailing items as separate answer rows.
    return [exam_numbers, [normalize_answer_pattern(x) for x in entry[1:]]]


def repair_brackets(text):
    """
    Append missing closing brackets/braces to loosely formatted text.

    This helper is used when parsing malformed or truncated key fragments where
    closing delimiters may be missing.

    Parameters:
        text (str): Input text to repair.

    Returns:
        str: Text with missing closing square/curly brackets appended.
    """
    stripped = text.strip()

    opens_curly = stripped.count("{")
    closes_curly = stripped.count("}")
    opens_square = stripped.count("[")
    closes_square = stripped.count("]")

    if opens_square > closes_square:
        stripped += "]" * (opens_square - closes_square)

    if opens_curly > closes_curly:
        stripped += "}" * (opens_curly - closes_curly)

    return stripped


def extract_generated_on(text):
    """
    Extract the generation timestamp from a key-text blob.

    Supported timestamp fields:
    - 'g'
    - 'generated_on'

    Parameters:
        text (str): Raw key text.

    Returns:
        str: Extracted timestamp, or an empty string if not found.
    """
    m = re.search(r"""['"]g['"]\s*:\s*['"]([^'"]+)['"]""", text)
    if m:
        return m.group(1)

    m = re.search(r"""['"]generated_on['"]\s*:\s*['"]([^'"]+)['"]""", text)
    if m:
        return m.group(1)

    return ""


def split_loose_k_entries(text):
    """
    Split a loose 'k' section into individual top-level entries.

    This parser tracks:
    - list nesting depth
    - quoted strings

    so that top-level entry boundaries can be identified safely.

    Parameters:
        text (str): Raw text containing one or more compact key entries.

    Returns:
        list[str]: Extracted entry strings.
    """
    entries = []
    current = []
    depth = 0
    in_string = False
    quote_char = ""

    i = 0
    while i < len(text):
        ch = text[i]

        if in_string:
            current.append(ch)
            if ch == quote_char and (i == 0 or text[i - 1] != "\\"):
                in_string = False
            i += 1
            continue

        if ch in ("'", '"'):
            in_string = True
            quote_char = ch
            current.append(ch)
            i += 1
            continue

        if ch == "[":
            depth += 1
        elif ch == "]":
            depth -= 1

        current.append(ch)

        if depth == 0 and "".join(current).strip():
            candidate = "".join(current).strip()

            # Skip separators between entries.
            j = i + 1
            while j < len(text) and text[j] in " \n\r\t,":
                j += 1

            if candidate:
                entries.append(candidate.rstrip(","))
                current = []
                i = j
                continue

        i += 1

    tail = "".join(current).strip().rstrip(",")
    if tail:
        entries.append(tail)

    return [e for e in entries if e]


def parse_compact_entry_text(entry_text):
    """
    Parse one compact solution-key entry from text.

    Expected structure:
        [[exam_numbers], answer_pattern_1, answer_pattern_2, ...]

    Answer patterns may appear as:
    - lists
    - quoted strings
    - raw bitstrings

    Parameters:
        entry_text (str): Raw compact entry text.

    Returns:
        list: Normalized solution entry in the form:
            [exam_numbers, answer_rows]

    Raises:
        ValueError: If the entry is malformed or contains unsupported tokens.
    """
    text = entry_text.strip()
    if not (text.startswith("[") and text.endswith("]")):
        raise ValueError(f"Malformed key entry: {entry_text}")

    inner = text[1:-1].strip()

    if not inner.startswith("["):
        raise ValueError(f"Entry does not start with exam number list: {entry_text}")

    # Find the end of the leading exam-number list.
    depth = 0
    split_index = None
    for i, ch in enumerate(inner):
        if ch == "[":
            depth += 1
        elif ch == "]":
            depth -= 1
            if depth == 0:
                split_index = i
                break

    if split_index is None:
        raise ValueError(f"Could not parse exam number list in entry: {entry_text}")

    exam_part = inner[:split_index + 1]
    rest = inner[split_index + 1:].strip()

    exam_numbers = ast.literal_eval(exam_part)
    if not isinstance(exam_numbers, list):
        raise ValueError("Exam numbers must be a list.")

    if rest.startswith(","):
        rest = rest[1:].strip()

    if not rest:
        raise ValueError("No answer patterns found after exam numbers.")

    # Split the remaining text into top-level answer tokens.
    tokens = []
    current = []
    depth = 0
    in_string = False
    quote_char = ""

    i = 0
    while i < len(rest):
        ch = rest[i]

        if in_string:
            current.append(ch)
            if ch == quote_char and (i == 0 or rest[i - 1] != "\\"):
                in_string = False
            i += 1
            continue

        if ch in ("'", '"'):
            in_string = True
            quote_char = ch
            current.append(ch)
            i += 1
            continue

        if ch == "[":
            depth += 1
        elif ch == "]":
            depth -= 1

        if ch == "," and depth == 0:
            token = "".join(current).strip()
            if token:
                tokens.append(token)
            current = []
            i += 1
            continue

        current.append(ch)
        i += 1

    token = "".join(current).strip()
    if token:
        tokens.append(token)

    solutions = []
    for token in tokens:
        if token.startswith("["):
            value = ast.literal_eval(repair_brackets(token))
            solutions.append(normalize_answer_pattern(value))
        elif (token.startswith("'") and token.endswith("'")) or (
            token.startswith('"') and token.endswith('"')
        ):
            value = ast.literal_eval(token)
            solutions.append(normalize_answer_pattern(value))
        elif re.fullmatch(r"[01]+", token):
            solutions.append(normalize_answer_pattern(token))
        else:
            raise ValueError(f"Unsupported answer token: {token}")

    return [exam_numbers, solutions]


def parse_loose_k_format(raw_text):
    """
    Parse a loosely formatted solution-key dictionary containing a 'k' block.

    This fallback parser is used when direct literal parsing fails but the text
    still appears to contain compact key entries.

    Parameters:
        raw_text (str): Raw solution-key text.

    Returns:
        dict: Normalized dictionary containing:
            - generated_on
            - keys

    Raises:
        ValueError: If the 'k' block cannot be found.
    """
    generated_on = extract_generated_on(raw_text)

    m = re.search(r"""['"]k['"]\s*:\s*(.*)$""", raw_text, re.DOTALL)
    if not m:
        raise ValueError("Could not find 'k' block.")

    k_block = m.group(1).strip()

    if k_block.endswith("}"):
        k_block = k_block[:-1].rstrip()

    entries_text = split_loose_k_entries(k_block)
    keys = [parse_compact_entry_text(entry) for entry in entries_text]

    return {
        "generated_on": generated_on,
        "keys": keys,
    }


def read_single_test(image, grid_structure, color_thr_sensitivity=2):
    """
    Read one answer sheet image and extract its answer matrix.

    This function:
    - estimates image brightness/color statistics,
    - computes adaptive thresholds,
    - locates sheet corners and marker pairs,
    - reads the answer grid.

    Parameters:
        image (numpy.ndarray): Input answer-sheet image.
        grid_structure (list[int]): Number of answer choices for each question.
        color_thr_sensitivity (int, optional): Sensitivity factor used when
            computing color thresholds.

    Returns:
        list | object: Extracted answer matrix. If the downstream reader returns
        a dictionary, only its "answer_matrix" field is returned.
    """
    img = image

    h_markers_number = len(grid_structure)
    w_markers_number = max(grid_structure)

    img_height = img.shape[0]
    img_width = img.shape[1]

    # First pass: estimate global image statistics.
    temp_analyzer = ImageAnalyzer(img, grey_threshold=0, color_threshold=[0, 0, 0])
    avg_grey, avg_color = temp_analyzer.avg_grey_and_color()

    tst_sqr_size = img_width // 60
    grey_of_dark, color_of_dark = gr_and_color_of_dark(temp_analyzer, tst_sqr_size)

    # Build adaptive thresholds based on the detected dark-marker region.
    grey_threshold = current_grey_threshold(grey_of_dark, avg_grey)
    color_threshold = [
        current_color_threshold(color_of_dark[i], avg_color[i], color_thr_sensitivity)
        for i in range(3)
    ]

    analyzer = ImageAnalyzer(img, grey_threshold, color_threshold)

    step_size = max(1, img_width // 110)
    ctr_border = min(img_height, img_width) // step_size

    # Locate the four main reference corners of the answer sheet.
    corners = locate_corners(analyzer, step_size, ctr_border, grey_threshold)
    origin = corners[0]
    dl_corner = corners[1]
    ur_corner = corners[2]
    dr_corner = corners[3]

    # Estimate marker size from the origin marker dimensions.
    origin_data = analyzer.center_height_width(origin, grey_threshold)
    origin_height = origin_data[1]
    origin_width = origin_data[2]
    marker_size = round((origin_height + origin_width) / 2)

    # Use the corner/marker geometry to identify the answer-grid layout.
    marker_pairs = locate_marker_pairs(
        analyzer,
        ctr_border,
        origin,
        origin_height,
        origin_width,
        ur_corner,
        dl_corner,
        dr_corner,
        h_markers_number,
        w_markers_number,
        grey_threshold,
    )

    answer_data = read_answer_grid(
        analyzer,
        marker_pairs,
        h_markers_number,
        marker_size,
        grid_structure,
        color_threshold,
    )

    print("Grading the next test ...")

    if isinstance(answer_data, dict):
        return answer_data["answer_matrix"]

    return answer_data


def read_single_test_detailed(image, grid_structure, color_thr_sensitivity=2):
    """
    Read one answer sheet image and return detailed grading-detection data.

    In addition to the answer matrix, this function returns:
    - per-box detections,
    - a copy of the source image for reporting,
    - estimated marker size.

    Parameters:
        image (numpy.ndarray): Input answer-sheet image.
        grid_structure (list[int]): Number of answer choices for each question.
        color_thr_sensitivity (int, optional): Sensitivity factor used when
            computing color thresholds.

    Returns:
        dict: Dictionary containing:
            - answer_matrix
            - detections
            - image_for_pdf
            - marker_size
    """
    img = image

    h_markers_number = len(grid_structure)
    w_markers_number = max(grid_structure)

    img_height = img.shape[0]
    img_width = img.shape[1]

    # First pass: estimate image statistics before setting thresholds.
    temp_analyzer = ImageAnalyzer(img, grey_threshold=0, color_threshold=[0, 0, 0])
    avg_grey, avg_color = temp_analyzer.avg_grey_and_color()

    tst_sqr_size = img_width // 60
    grey_of_dark, color_of_dark = gr_and_color_of_dark(temp_analyzer, tst_sqr_size)

    grey_threshold = current_grey_threshold(grey_of_dark, avg_grey)
    color_threshold = [
        current_color_threshold(color_of_dark[i], avg_color[i], color_thr_sensitivity)
        for i in range(3)
    ]

    analyzer = ImageAnalyzer(img, grey_threshold, color_threshold)

    step_size = max(1, img_width // 110)
    ctr_border = min(img_height, img_width) // step_size

    corners = locate_corners(analyzer, step_size, ctr_border, grey_threshold)
    origin = corners[0]
    dl_corner = corners[1]
    ur_corner = corners[2]
    dr_corner = corners[3]

    origin_data = analyzer.center_height_width(origin, grey_threshold)
    origin_height = origin_data[1]
    origin_width = origin_data[2]
    marker_size = round((origin_height + origin_width) / 2)

    marker_pairs = locate_marker_pairs(
        analyzer,
        ctr_border,
        origin,
        origin_height,
        origin_width,
        ur_corner,
        dl_corner,
        dr_corner,
        h_markers_number,
        w_markers_number,
        grey_threshold,
    )

    answer_data = read_answer_grid(
        analyzer,
        marker_pairs,
        h_markers_number,
        marker_size,
        grid_structure,
        color_threshold,
    )

    print("Grading the next test ...")

    if isinstance(answer_data, dict):
        answer_matrix = answer_data.get("answer_matrix", [])
        detections = answer_data.get("detections", [])
    else:
        answer_matrix = answer_data
        detections = []

    return {
        "answer_matrix": answer_matrix,
        "detections": detections,
        "image_for_pdf": img.copy(),
        "marker_size": marker_size,
    }


def read_tests(converted_pages, grid_structure, color_thr_sensitivity=2):
    """
    Read multiple test pages and return their answer matrices.

    Parameters:
        converted_pages (list): List of page images, either already as numpy
            arrays or as PIL images.
        grid_structure (list[int]): Number of answer choices for each question.
        color_thr_sensitivity (int, optional): Sensitivity factor used when
            computing color thresholds.

    Returns:
        list: One extracted answer matrix per page.
    """
    pages = converted_pages
    answer_grids = []

    for page in pages:
        if isinstance(page, np.ndarray):
            img = page
        else:
            img = np.array(page)

        answer_grids.append(read_single_test(img, grid_structure, color_thr_sensitivity))

    return answer_grids


def read_tests_detailed(converted_pages, grid_structure, color_thr_sensitivity=2):
    """
    Read multiple test pages and return detailed extraction data for each page.

    Parameters:
        converted_pages (list): List of page images, either already as numpy
            arrays or as PIL images.
        grid_structure (list[int]): Number of answer choices for each question.
        color_thr_sensitivity (int, optional): Sensitivity factor used when
            computing color thresholds.

    Returns:
        list[dict]: One detailed extraction-result dictionary per page.
    """
    pages = converted_pages
    results = []

    for page in pages:
        if isinstance(page, np.ndarray):
            img = page
        else:
            img = np.array(page)

        results.append(
            read_single_test_detailed(img, grid_structure, color_thr_sensitivity)
        )

    return results


def load_solution_keys(text_file_path):
    """
    Load and normalize solution keys from a text file.

    Supported forms include:
    - standard Python-literal dictionaries
    - compact dictionaries using 'g'/'k'
    - loosely formatted compact key text

    The returned structure is normalized to:
        {
            "generated_on": ...,
            "keys": [...]
        }

    Parameters:
        text_file_path (str): Path to the solution-key text file.

    Returns:
        dict: Normalized solution-key dictionary.

    Raises:
        ValueError: If required fields are missing or malformed.
    """
    with open(text_file_path, "r", encoding="utf-8") as f:
        raw_text = f.read().strip()

    repaired = repair_brackets(raw_text)

    try:
        solution_keys = ast.literal_eval(repaired)
    except Exception:
        return parse_loose_k_format(raw_text)

    if not isinstance(solution_keys, dict):
        raise ValueError("Solution key file must contain a dictionary.")

    # Support the compact field names generated elsewhere in the project.
    if "k" in solution_keys:
        solution_keys = {
            "generated_on": solution_keys.get("g", ""),
            "keys": solution_keys["k"],
        }

    if "keys" not in solution_keys:
        raise ValueError("Solution key file is missing the 'keys' field.")

    if "generated_on" not in solution_keys:
        raise ValueError("Solution key file is missing the 'generated_on' field.")

    raw_keys = solution_keys["keys"]

    if not isinstance(raw_keys, list):
        raise ValueError("The 'keys' field must be a list.")

    if not raw_keys:
        return {
            "generated_on": solution_keys["generated_on"],
            "keys": [],
        }

    # Support both:
    # - a single key entry stored directly
    # - a list of multiple key entries
    if (
        isinstance(raw_keys[0], list)
        and all(isinstance(x, int) for x in raw_keys[0])
        and len(raw_keys) >= 2
    ):
        normalized_keys = [normalize_solution_entry(raw_keys)]
    else:
        normalized_keys = [normalize_solution_entry(entry) for entry in raw_keys]

    return {
        "generated_on": solution_keys["generated_on"],
        "keys": normalized_keys,
    }


def group_detections_by_question(detections, marker_size):
    """
    Group per-choice detections by question and attach drawing-box metadata.

    This is mainly used for report generation so that each detected answer box
    can be visualized consistently on the output image/PDF.

    Parameters:
        detections (list[dict]): Raw detection records.
        marker_size (int): Estimated marker size used to scale visualization boxes.

    Returns:
        list[dict]: A list of question dictionaries, each containing:
            - question_number
            - boxes
    """
    grouped = {}

    box_w = max(6, marker_size // 2)
    box_h = max(6, marker_size // 2)

    for det in detections:
        qn = det["question_number"]
        if qn not in grouped:
            grouped[qn] = []

        cy, cx = det["center"]

        grouped[qn].append({
            "choice_index": det["choice_index"],
            "x": int(cx - box_w // 2),
            "y": int(cy - box_h // 2),
            "w": int(box_w),
            "h": int(box_h),
            "center_x": int(cx),
            "center_y": int(cy),
            "is_filled": bool(det["filled"]),
        })

    questions = []
    for qn in sorted(grouped.keys()):
        boxes = sorted(grouped[qn], key=lambda b: b["choice_index"])
        questions.append({
            "question_number": qn,
            "boxes": boxes,
        })

    return questions


def grade_tests(
    image_path,
    text_file_path,
    weights,
    manual_test_number=None,
    color_thr_sensitivity=4,
):
    """
    Grade one or more answer sheets and return text-oriented grade summaries.

    Parameters:
        image_path (str): Path to the input PDF or image file.
        text_file_path (str): Path to the solution-key file.
        weights (list[int | float]): Per-question weights.
        manual_test_number (int, optional): Test number to use when grading a
            single image input.
        color_thr_sensitivity (int, optional): Sensitivity factor used during
            answer-box detection.

    Returns:
        list[list[str, str]]: Grade summaries in the form:
            [test label, grade text]
    """
    loaded_pages = load_input_pages(image_path)
    file_path = text_file_path
    solution_keys = load_solution_keys(file_path)
    keys = solution_keys["keys"]
    solutions = keys[0][1]
    grid_structure = [len(sol) for sol in solutions]

    answers = read_tests(loaded_pages, grid_structure, color_thr_sensitivity)
    grades = []

    for i in range(len(answers)):
        if manual_test_number is not None:
            test_number = manual_test_number
        else:
            test_number = i + 1
            print(f"Grading test No. {i + 1} ...")

        answer_grid = answers[i]
        matched = False

        # Select the solution-key variant assigned to this test number.
        for j in range(len(keys)):
            exam_numbers = keys[j][0]
            current_solutions = keys[j][1]

            if test_number in exam_numbers:
                grade = total_grade_single(answer_grid, current_solutions, weights)
                grades.append([f"test number {test_number}", f"has grade {grade}"])
                matched = True
                break

        if not matched:
            grades.append([f"test number {test_number}", "has no matching solution key"])

    return grades


def grade_tests_with_details(
    image_path,
    text_file_path,
    weights,
    manual_test_number=None,
    color_thr_sensitivity=4,
):
    """
    Grade one or more answer sheets and return detailed reporting data.

    In addition to text summaries, this function packages enough information for
    later PDF/TXT reporting, including:
    - the original image,
    - detected answer boxes,
    - the per-question student answer and correct key,
    - correctness flags.

    Parameters:
        image_path (str): Path to the input PDF or image file.
        text_file_path (str): Path to the solution-key file.
        weights (list[int | float]): Per-question weights.
        manual_test_number (int, optional): Test number to use when grading a
            single image input.
        color_thr_sensitivity (int, optional): Sensitivity factor used during
            answer-box detection.

    Returns:
        dict: Dictionary containing:
            - grades: text summaries
            - tests: detailed per-test report data

    Raises:
        ValueError: If no solution keys are found.
    """
    loaded_pages = load_input_pages(image_path)
    solution_keys = load_solution_keys(text_file_path)
    keys = solution_keys["keys"]

    if not keys:
        raise ValueError("No solution keys found.")

    solutions = keys[0][1]
    grid_structure = [len(sol) for sol in solutions]

    detailed_answers = read_tests_detailed(
        loaded_pages,
        grid_structure,
        color_thr_sensitivity,
    )

    grades = []
    tests = []

    for i, test_data in enumerate(detailed_answers):
        if manual_test_number is not None:
            test_number = manual_test_number
        else:
            test_number = i + 1
            print(f"Grading test No. {i + 1} ...")

        answer_matrix = test_data["answer_matrix"]
        question_boxes = group_detections_by_question(
            test_data["detections"],
            test_data["marker_size"],
        )

        matched = False

        # Select the solution-key variant assigned to this test number.
        for j in range(len(keys)):
            exam_numbers = keys[j][0]
            current_solutions = keys[j][1]

            if test_number in exam_numbers:
                grade = total_grade_single(answer_matrix, current_solutions, weights)

                questions = []
                for q_idx, (ans, key) in enumerate(
                    zip(answer_matrix, current_solutions),
                    start=1,
                ):
                    box_info = []
                    if q_idx - 1 < len(question_boxes):
                        box_info = question_boxes[q_idx - 1]["boxes"]

                    questions.append({
                        "question_number": q_idx,
                        "answer": ans,
                        "key": key,
                        "is_correct": ans == key,
                        "boxes": box_info,
                    })

                grades.append([f"test number {test_number}", f"has grade {grade}"])
                tests.append({
                    "test_number": test_number,
                    "grade": grade,
                    "image_for_pdf": test_data["image_for_pdf"],
                    "questions": questions,
                })
                matched = True
                break

        if not matched:
            grades.append([f"test number {test_number}", "has no matching solution key"])
            tests.append({
                "test_number": test_number,
                "grade": None,
                "image_for_pdf": test_data["image_for_pdf"],
                "questions": [],
            })

    return {
        "grades": grades,
        "tests": tests,
    }
