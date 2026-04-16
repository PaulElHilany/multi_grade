"""
Adapter utilities connecting the mobile UI to the grading backend.

This module provides:
- solution-key text normalization,
- temporary file creation/cleanup for key data,
- question-weight validation,
- conversion of grading results into a structured format suitable for the mobile UI.

It acts as a bridge between the Kivy UI and the multi_grade_mobile backend.
"""

import ast
import os
import re
import tempfile


def _import_multi_grade_mobile():
    """
    Import the mobile grading backend lazily.

    Returns:
        tuple[callable, callable]:
            - grade_tests function
            - load_solution_keys function

    Raises:
        ModuleNotFoundError: If the mobile grading backend or one of its
            dependencies is missing.
    """
    try:
        from multi_grade_mobile import grade_tests, load_solution_keys
        return grade_tests, load_solution_keys
    except ModuleNotFoundError as e:
        raise ModuleNotFoundError(
            f"Required grading dependency is missing: {e}"
        ) from e


def parse_weights_text(text):
    """
    Parse and validate a Python-literal weight list.

    Parameters:
        text (str): Raw weight-list text.

    Returns:
        list[int | float]: Parsed numeric weights.

    Raises:
        ValueError: If the text is invalid, empty, not a list, or contains
            non-numeric values.
    """
    try:
        value = ast.literal_eval(text)
    except Exception as e:
        raise ValueError(f"Invalid weights format: {e}")

    if not isinstance(value, list):
        raise ValueError("Weights must be a list.")

    if len(value) == 0:
        raise ValueError("Weights list must not be empty.")

    for i, item in enumerate(value):
        if not isinstance(item, (int, float)):
            raise ValueError(
                f"Invalid value at weights[{i}]: {item}. Weights must be numbers."
            )

    return value


def _looks_like_python_literal_keys(text):
    """
    Heuristically detect whether the key text looks like a Python literal.

    Parameters:
        text (str): Raw key text.

    Returns:
        bool: True if the text begins like a Python literal structure.
    """
    stripped = text.strip()
    if not stripped:
        return False
    return stripped.startswith("[") or stripped.startswith("(") or stripped.startswith("{")


def _parse_bitstring(token):
    """
    Convert a bitstring token into a list of integers.

    Example:
        "1010" -> [1, 0, 1, 0]

    Parameters:
        token (str): Bitstring containing only 0 and 1 characters.

    Returns:
        list[int]: Parsed bits.

    Raises:
        ValueError: If the token is empty or invalid.
    """
    token = token.strip()
    if not token:
        raise ValueError("Empty bitstring encountered.")
    if not re.fullmatch(r"[01]+", token):
        raise ValueError(f"Invalid bitstring '{token}'. Only 0 and 1 are allowed.")
    return [int(ch) for ch in token]


def _split_compact_rows(k_body):
    """
    Split the compact key body into individual row strings.

    Parameters:
        k_body (str): Raw compact 'k' body text.

    Returns:
        list[str]: Individual row strings.
    """
    rows = []
    current = []
    depth = 0

    for ch in k_body:
        if ch == "[":
            depth += 1
        elif ch == "]":
            depth -= 1

        current.append(ch)

        if depth == 0:
            chunk = "".join(current).strip().rstrip(",").strip()
            if chunk:
                rows.append(chunk)
            current = []

    trailing = "".join(current).strip().rstrip(",").strip()
    if trailing:
        rows.append(trailing)

    return rows


def _parse_compact_row(row_text):
    """
    Parse one compact solution-key row.

    Expected structure:
        [[test_numbers], bitstring1, bitstring2, ...]

    Parameters:
        row_text (str): One row of compact key text.

    Returns:
        list: Parsed row in the form:
            [test_numbers, answer_rows]

    Raises:
        ValueError: If the row is malformed.
    """
    row_text = row_text.strip().rstrip(",")

    if not row_text.startswith("[") or not row_text.endswith("]"):
        raise ValueError(f"Invalid compact row: {row_text}")

    inner = row_text[1:-1].strip()

    if not inner.startswith("["):
        raise ValueError(f"Compact row must start with a test-number list: {row_text}")

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
        raise ValueError(f"Could not parse test-number list in row: {row_text}")

    test_numbers_text = inner[:split_index + 1]
    remainder = inner[split_index + 1:].strip()

    if remainder.startswith(","):
        remainder = remainder[1:].strip()

    try:
        test_numbers = ast.literal_eval(test_numbers_text)
    except Exception as e:
        raise ValueError(f"Invalid test-number list in compact row: {e}")

    if not isinstance(test_numbers, list) or not all(isinstance(x, int) for x in test_numbers):
        raise ValueError("Compact row test-number part must be a list of integers.")

    tokens = [t.strip() for t in remainder.split(",") if t.strip()]
    if not tokens:
        raise ValueError("Compact row must contain at least one bitstring.")

    answer_rows = [_parse_bitstring(token) for token in tokens]
    return [test_numbers, answer_rows]


def _normalize_compact_keys_text(text):
    """
    Normalize compact custom key text into a Python-literal dictionary string.

    Parameters:
        text (str): Raw compact key text.

    Returns:
        str: Normalized dictionary string using compact 'g'/'k' fields.

    Raises:
        ValueError: If the text is malformed.
    """
    text = text.strip()

    g_match = re.search(r"'(?:g|lg)'\s*:\s*'([^']*)'", text)
    if not g_match:
        raise ValueError("Compact keys text must contain a 'g' or 'lg' timestamp.")

    g_value = g_match.group(1)

    k_pos_match = re.search(r"'k'\s*:", text)
    if not k_pos_match:
        raise ValueError("Compact keys text must contain a 'k' section.")

    k_start = k_pos_match.end()
    tail = text[k_start:].strip()

    if tail.endswith("}"):
        tail = tail[:-1].rstrip()

    # Accept an extra outer bracket layer around the row list.
    if tail.startswith("[") and tail.endswith("]"):
        inner = tail[1:-1].strip()
        if inner.startswith("[["):
            tail = inner

    rows = _split_compact_rows(tail)
    if not rows:
        raise ValueError("No compact rows found in 'k' section.")

    parsed_rows = [_parse_compact_row(row) for row in rows]

    normalized = {
        "g": g_value,
        "k": parsed_rows,
    }
    return repr(normalized)


def _normalize_simple_keys_text(text):
    """
    Normalize simple row-based key text into a Python list string.

    Supported input examples:
        1 0 1
        0 1 0

    or:
        1,0,1
        0,1,0

    Parameters:
        text (str): Raw key text.

    Returns:
        str: Normalized list string.

    Raises:
        ValueError: If the text is empty, malformed, or inconsistent in width.
    """
    text = text.strip()
    if not text:
        raise ValueError("Solution keys text is empty.")

    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines:
        raise ValueError("Solution keys text is empty.")

    parsed_rows = []

    for line in lines:
        parts = [p for p in re.split(r"[,\s]+", line) if p]
        if not parts:
            continue

        row = []
        for part in parts:
            try:
                row.append(int(part))
            except ValueError:
                raise ValueError(
                    f"Invalid solution-key value '{part}'. "
                    f"Use integers separated by commas or spaces."
                )

        parsed_rows.append(row)

    if not parsed_rows:
        raise ValueError("No valid solution-key rows were found.")

    row_lengths = {len(row) for row in parsed_rows}
    if len(row_lengths) != 1:
        raise ValueError(
            "All solution-key rows must contain the same number of values."
        )

    return str(parsed_rows)


def normalize_keys_text(text):
    """
    Normalize solution-key text into a standard Python-literal format.

    Supported input styles include:
    - compact custom key format
    - Python-literal structures
    - simple row-based numeric key formats

    Parameters:
        text (str): Raw solution-key text.

    Returns:
        str: Normalized key text.

    Raises:
        ValueError: If the text is empty or unsupported.
    """
    text = text.strip()
    if not text:
        raise ValueError("Solution keys text is empty.")

    if "'k'" in text and re.search(r"\[\[[0-9,\s]+\],\s*[01]{2,}", text):
        return _normalize_compact_keys_text(text)

    if ("'g'" in text or "'lg'" in text) and "'k'" in text:
        try:
            return _normalize_compact_keys_text(text)
        except Exception:
            pass

    if _looks_like_python_literal_keys(text):
        try:
            ast.literal_eval(text)
            return text
        except Exception:
            raise ValueError(f"Invalid Python-literal solution keys format: {text[:120]}...")

    return _normalize_simple_keys_text(text)


def save_keys_text_to_temp_file(qr_text):
    """
    Normalize solution-key text and save it to a temporary file.

    Parameters:
        qr_text (str): Raw key text, typically pasted from a QR reader result.

    Returns:
        str: Path to the created temporary file.

    Raises:
        ValueError: If the input text is empty or invalid.
    """
    qr_text = qr_text.strip()
    if not qr_text:
        raise ValueError("Solution keys text is empty.")

    normalized_text = normalize_keys_text(qr_text)

    with tempfile.NamedTemporaryFile(
        mode="w",
        delete=False,
        suffix=".txt",
        encoding="utf-8"
    ) as f:
        f.write(normalized_text)
        return f.name


def expected_question_count(keys_path):
    """
    Load normalized key data and return the expected question count.

    Parameters:
        keys_path (str): Path to the normalized key file.

    Returns:
        int: Number of questions in the first solution set.

    Raises:
        ValueError: If no key sets are available.
    """
    _, load_solution_keys = _import_multi_grade_mobile()

    solution_keys = load_solution_keys(keys_path)
    keys = solution_keys["keys"]

    if not keys:
        raise ValueError("No keys found in the solution key data.")

    first_solution_set = keys[0][1]
    return len(first_solution_set)


def validate_weights_against_keys(keys_path, weights):
    """
    Validate that the number of weights matches the number of questions.

    Parameters:
        keys_path (str): Path to the normalized key file.
        weights (list[int | float]): Weight values to validate.

    Raises:
        ValueError: If the number of weights does not match the number of questions.
    """
    question_count = expected_question_count(keys_path)

    if len(weights) != question_count:
        raise ValueError(
            f"Number of weights ({len(weights)}) does not match "
            f"the number of questions ({question_count})."
        )


def parse_grade_value(grade_text):
    """
    Extract a numeric grade value from a grade-summary string.

    Example supported input:
        "test number 3 has grade 8.5"

    Parameters:
        grade_text (str): Grade-summary text.

    Returns:
        float | None: Parsed grade value if found, otherwise None.
    """
    match = re.search(r"has grade\s+([0-9]+(?:\.[0-9]+)?)", grade_text)
    if match:
        return float(match.group(1))
    return None


def grade_single_test_structured(
    image_path,
    keys_path,
    weights,
    test_number,
    color_thr_sensitivity=4,
):
    """
    Grade one test image and convert the backend output into a structured dictionary.

    Parameters:
        image_path (str): Path to the test image.
        keys_path (str): Path to the normalized key file.
        weights (list[int | float]): Per-question weights.
        test_number (int): Test number associated with the image.
        color_thr_sensitivity (int, optional): Color-threshold sensitivity.

    Returns:
        dict: Structured grading result used by the mobile UI.

    Raises:
        ValueError: If no grading result is returned.
        TypeError: If the backend returns an unexpected result type.
    """
    grade_tests, _ = _import_multi_grade_mobile()

    grades = grade_tests(
        image_path,
        keys_path,
        weights,
        manual_test_number=test_number,
        color_thr_sensitivity=color_thr_sensitivity,
    )

    if not grades:
        raise ValueError("No grading result was returned.")

    if isinstance(grades, dict):
        row = grades
    elif isinstance(grades, list):
        row = grades[0]
    else:
        raise TypeError("Unexpected grading result type.")

    return {
        "test_number": row.get("test_number", test_number),
        "grade": row.get("grade"),
        "left_text": row.get("left_text", f"test number {test_number}"),
        "right_text": row.get("right_text", ""),
        "display_text": row.get("display_text", ""),
        "questions": row.get("questions", []),
        "student_answers": row.get("student_answers", []),
        "matched_solution_exam_numbers": row.get("matched_solution_exam_numbers", []),
        "status": row.get("status", "ok"),
        "detections": row.get("detections", []),
        "image_shape": row.get("image_shape", []),
        "image_path": row.get("image_path"),
    }


def cleanup_temp_file(path):
    """
    Delete a temporary file if it exists.

    Parameters:
        path (str | None): File path to remove.
    """
    if path and os.path.exists(path):
        os.remove(path)
