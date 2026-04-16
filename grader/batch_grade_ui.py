"""
Tkinter desktop UI for batch grading multiple-choice answer sheets.

This module provides:
- validation/parsing of question weights,
- parsing and normalization of different solution-key text formats,
- file-browsing helpers for the desktop interface,
- execution of the batch grading workflow,
- saving grading results and generated reports.

It supports:
- PDF batch grading,
- single-image grading with manual test-number entry,
- pasted or file-based solution keys,
- TXT and PDF result export.
"""

import ast
import os
import re
import tempfile
import traceback
from datetime import datetime

import tkinter as tk
from tkinter import ttk, messagebox, filedialog

from multi_grade import grade_tests_with_details, load_solution_keys
from batch_reporting import export_results_pdf, export_results_txt


def parse_weights_text(text):
    """
    Parse and validate the question-weights text entered by the user.

    The expected format is a Python list of numeric values, for example:
        [1, 1, 2, 1.5]

    Parameters:
        text (str): Raw text entered by the user.

    Returns:
        list[int | float]: Parsed list of numeric weights.

    Raises:
        ValueError: If the text is invalid, empty, not a list, or contains
            non-numeric values.
    """
    try:
        # Safely parse the text as a Python literal.
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
    Heuristically detect whether solution-key text looks like a Python literal.

    This is used to distinguish Python-style structures such as:
        [...]
        (...)
        {...}

    from simpler text formats.

    Parameters:
        text (str): Raw solution-key text.

    Returns:
        bool: True if the stripped text begins like a Python literal.
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
        token (str): Input bitstring containing only 0 and 1 characters.

    Returns:
        list[int]: Parsed bit values.

    Raises:
        ValueError: If the token is empty or contains characters other than 0 or 1.
    """
    token = token.strip()
    if not token:
        raise ValueError("Empty bitstring encountered.")
    if not re.fullmatch(r"[01]+", token):
        raise ValueError(f"Invalid bitstring '{token}'. Only 0 and 1 are allowed.")
    return [int(ch) for ch in token]


def _extract_compact_k_tail(text):
    """
    Extract the timestamp and raw 'k' section from compact key text.

    The compact key format is expected to contain:
    - a generation timestamp under 'g' or 'lg'
    - a key section under 'k'

    Parameters:
        text (str): Raw compact key text.

    Returns:
        tuple[str, str]:
            - timestamp value
            - raw text following the 'k' section label

    Raises:
        ValueError: If the expected timestamp or key section is missing.
    """
    g_match = re.search(r"'(?:g|lg)'\s*:\s*'([^']*)'", text)
    if not g_match:
        raise ValueError("Compact keys text must contain a 'g' or 'lg' timestamp.")
    g_value = g_match.group(1)

    k_match = re.search(r"'k'\s*:", text)
    if not k_match:
        raise ValueError("Compact keys text must contain a 'k' section.")

    tail = text[k_match.end():].strip()

    # Remove a trailing closing brace if present so only the row content remains.
    if tail.endswith("}"):
        tail = tail[:-1].rstrip()

    return g_value, tail


def _split_compact_rows(k_body):
    """
    Split the compact 'k' section into individual row strings.

    This parser walks through the text character by character and keeps track of:
    - bracket nesting depth
    - quoted strings

    so that top-level row blocks can be extracted safely.

    Parameters:
        k_body (str): Raw body text of the compact 'k' section.

    Returns:
        list[str]: Individual compact row strings.

    Raises:
        ValueError: If malformed row structure is encountered.
    """
    rows = []
    i = 0
    n = len(k_body)

    while i < n:
        # Skip whitespace and separating commas between rows.
        while i < n and k_body[i] in " \t\r\n,":
            i += 1

        if i >= n:
            break

        if k_body[i] != "[":
            raise ValueError(f"Expected '[' at position {i} while parsing compact rows.")

        start = i
        depth = 0
        in_string = False
        quote_char = ""

        while i < n:
            ch = k_body[i]

            if in_string:
                if ch == quote_char and (i == 0 or k_body[i - 1] != "\\"):
                    in_string = False
                i += 1
                continue

            if ch in ("'", '"'):
                in_string = True
                quote_char = ch
                i += 1
                continue

            if ch == "[":
                depth += 1
            elif ch == "]":
                depth -= 1
                if depth == 0:
                    i += 1
                    break

            i += 1

        row = k_body[start:i].strip().rstrip(",").strip()
        if row:
            rows.append(row)

    return rows


def _split_top_level_csv(text):
    """
    Split a comma-separated string only at top-level commas.

    Commas inside nested lists or quoted strings are ignored.

    Parameters:
        text (str): Input text to split.

    Returns:
        list[str]: Top-level comma-separated items.
    """
    items = []
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

        if ch == "," and depth == 0:
            item = "".join(current).strip()
            if item:
                items.append(item)
            current = []
            i += 1
            continue

        current.append(ch)
        i += 1

    item = "".join(current).strip()
    if item:
        items.append(item)

    return items


def _parse_compact_row(row_text):
    """
    Parse one compact row of the custom key format.

    Expected structure:
        [[test_numbers], bitstring1, bitstring2, ...]

    Example:
        [[2], 111, 10, 1101]

    Parameters:
        row_text (str): One compact row as text.

    Returns:
        list: Parsed row in the form:
            [test_numbers, answer_rows]

    Raises:
        ValueError: If the row structure is invalid.
    """
    row_text = row_text.strip().rstrip(",")

    if not row_text.startswith("[") or not row_text.endswith("]"):
        raise ValueError(f"Invalid compact row: {row_text}")

    inner = row_text[1:-1].strip()

    if not inner.startswith("["):
        raise ValueError(f"Compact row must start with a test-number list: {row_text}")

    # Find the end of the first nested list, which contains the test numbers.
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

    tokens = _split_top_level_csv(remainder)
    if not tokens:
        raise ValueError("Compact row must contain at least one bitstring.")

    answer_rows = [_parse_bitstring(token) for token in tokens]
    return [test_numbers, answer_rows]


def _normalize_compact_keys_text(text):
    """
    Normalize compact custom key text into a Python-literal dictionary string.

    Output format:
        {'g': ..., 'k': ...}

    This normalized representation can then be passed to downstream loaders that
    expect a Python-literal structure.

    Parameters:
        text (str): Raw compact key text.

    Returns:
        str: Normalized Python-literal dictionary string.

    Raises:
        ValueError: If the compact text is malformed.
    """
    text = text.strip()
    g_value, tail = _extract_compact_k_tail(text)

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
    Normalize simple row-based solution-key text into a Python list string.

    Supported input examples:
        1 0 1
        0 1 0

    or:
        1,0,1
        0,1,0

    All rows must have the same number of values.

    Parameters:
        text (str): Raw simple key text.

    Returns:
        str: Normalized Python list string.

    Raises:
        ValueError: If the input is empty, malformed, or inconsistent in width.
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
    Normalize solution-key text into a Python-literal format accepted by the loader.

    Supported input styles include:
    - compact custom key format
    - Python-literal structures
    - simple row-based numeric formats

    The function tries to detect the format automatically and converts it into
    a normalized string representation.

    Parameters:
        text (str): Raw solution-key text.

    Returns:
        str: Normalized solution-key text.

    Raises:
        ValueError: If the input is empty or cannot be parsed as a supported format.
    """
    text = text.strip()
    if not text:
        raise ValueError("Solution keys text is empty.")

    # Detect the compact custom format using both the 'k' marker and a row pattern.
    if "'k'" in text and re.search(r"\[\[[0-9,\s]+\],\s*[01]{2,}", text):
        return _normalize_compact_keys_text(text)

    # Fall back to compact parsing for other likely compact-key variants.
    if ("'g'" in text or "'lg'" in text) and "'k'" in text:
        try:
            return _normalize_compact_keys_text(text)
        except Exception:
            pass

    # If the text looks like a Python literal, verify that it parses correctly.
    if _looks_like_python_literal_keys(text):
        try:
            ast.literal_eval(text)
            return text
        except Exception:
            raise ValueError(f"Invalid Python-literal solution keys format: {text[:120]}...")

    # Otherwise interpret the text as a simple row-based numeric format.
    return _normalize_simple_keys_text(text)


def expected_question_count(keys_path):
    """
    Determine the expected number of questions from a normalized solution-key file.

    Parameters:
        keys_path (str): Path to the normalized solution-key file.

    Returns:
        int: Number of questions in the first solution-key set.

    Raises:
        ValueError: If the loaded key data contains no key sets.
    """
    solution_keys = load_solution_keys(keys_path)
    keys = solution_keys["keys"]

    if not keys:
        raise ValueError("No keys found in the solution key file.")

    first_solution_set = keys[0][1]
    return len(first_solution_set)


def is_image_file(path):
    """
    Check whether a file path refers to a supported image file.

    Parameters:
        path (str): Input file path.

    Returns:
        bool: True if the file extension is .png, .jpg, or .jpeg.
    """
    ext = os.path.splitext(path)[1].lower()
    return ext in [".png", ".jpg", ".jpeg"]


def update_test_number_visibility(file_entry, test_number_label, test_number_entry):
    """
    Enable or disable manual test-number entry depending on the selected input file.

    Manual test numbers are required only when grading a single image file.
    For PDF batch input, the field is disabled.

    Parameters:
        file_entry (ttk.Entry): Entry containing the selected input path.
        test_number_label (ttk.Label): Label associated with the test-number field.
        test_number_entry (ttk.Entry): Entry used for manual test-number input.
    """
    path = file_entry.get().strip()
    enabled = is_image_file(path)
    state = "normal" if enabled else "disabled"

    test_number_label.config(foreground="black" if enabled else "gray")
    test_number_entry.config(state=state)

    if not enabled:
        test_number_entry.delete(0, tk.END)


def build_output_paths():
    """
    Build timestamped output paths for batch-grading result files.

    The output files are placed in a newly created timestamped folder relative
    to the current module location.

    Returns:
        tuple[str, str, str]:
            - output directory path
            - PDF results path
            - TXT log path
    """
    now = datetime.now()
    timestamp = now.strftime("%Y-%m-%d_%H-%M-%S")

    base_dir = os.path.dirname(os.path.abspath(__file__))
    output_dir = os.path.join(base_dir, f"generated_results_{timestamp}")
    os.makedirs(output_dir, exist_ok=True)

    pdf_path = os.path.join(output_dir, f"tests_read_{timestamp}.pdf")
    txt_path = os.path.join(output_dir, f"correction_log_{timestamp}.txt")

    return output_dir, pdf_path, txt_path


def browse_input_file(file_entry, test_number_label, test_number_entry):
    """
    Open a file dialog to choose the input PDF or image for grading.

    After selection, the UI updates the manual test-number field visibility
    according to whether the chosen file is an image.

    Parameters:
        file_entry (ttk.Entry): Entry to update with the selected file path.
        test_number_label (ttk.Label): Label for the manual test-number field.
        test_number_entry (ttk.Entry): Entry for the manual test number.
    """
    file_path = filedialog.askopenfilename(
        title="Select test sheets file",
        filetypes=[
            ("Supported files", "*.pdf *.jpeg *.jpg *.png"),
            ("PDF files", "*.pdf"),
            ("Image files", "*.jpeg *.jpg *.png"),
            ("All files", "*.*"),
        ],
    )
    if file_path:
        file_entry.delete(0, tk.END)
        file_entry.insert(0, file_path)
        update_test_number_visibility(file_entry, test_number_label, test_number_entry)


def browse_keys(keys_entry):
    """
    Open a file dialog to choose a solution-key file.

    Parameters:
        keys_entry (ttk.Entry): Entry to update with the selected file path.
    """
    file_path = filedialog.askopenfilename(
        title="Select solution key file",
        filetypes=[
            ("JSON/Text files", "*.json *.txt"),
            ("All files", "*.*"),
        ],
    )
    if file_path:
        keys_entry.delete(0, tk.END)
        keys_entry.insert(0, file_path)


def save_results(results_text_widget, status_label):
    """
    Save the displayed grading results to a user-selected TXT or CSV file.

    If a CSV filename is chosen, each displayed line is split into a compact
    two-column format:
    - test
    - grade_info

    Parameters:
        results_text_widget (tk.Text): Widget containing the displayed results.
        status_label (ttk.Label): Status label used for user feedback.

    Raises:
        ValueError: If there are no results to save.
    """
    try:
        content = results_text_widget.get("1.0", tk.END).strip()
        if not content:
            raise ValueError("There are no results to save.")

        file_path = filedialog.asksaveasfilename(
            title="Save grading results",
            defaultextension=".txt",
            filetypes=[
                ("Text files", "*.txt"),
                ("CSV files", "*.csv"),
                ("All files", "*.*"),
            ],
        )

        if not file_path:
            return

        if file_path.lower().endswith(".csv"):
            lines = [line.strip() for line in content.splitlines() if line.strip()]
            with open(file_path, "w", encoding="utf-8") as f:
                f.write("test,grade_info\n")
                for line in lines:
                    parts = line.split(" ", 3)
                    if len(parts) >= 4:
                        left = f"{parts[0]} {parts[1]} {parts[2]}"
                        right = parts[3]
                        f.write(f"\"{left}\",\"{right}\"\n")
                    else:
                        f.write(f"\"{line}\",\"\"\n")
        else:
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(content + "\n")

        status_label.config(text=f"Results saved to: {file_path}", foreground="green")
        messagebox.showinfo("Saved", f"Results saved to:\n{file_path}")

    except Exception as e:
        status_label.config(text="Failed to save results.", foreground="red")
        messagebox.showerror("Error", str(e))


def run_grading(
    file_entry,
    keys_entry,
    pasted_keys_text_widget,
    weights_text_widget,
    test_number_entry,
    input_mode_var,
    status_label,
    results_text,
):
    """
    Run the batch-grading workflow from the current UI state.

    This function:
    - validates the selected input file,
    - reads solution keys either from pasted text or from a file,
    - normalizes the key format into a temporary file,
    - validates question weights,
    - optionally reads a manual test number for image input,
    - calls the grading backend,
    - displays the computed grades,
    - exports PDF and TXT output files.

    Parameters:
        file_entry (ttk.Entry): Entry containing the selected test input file path.
        keys_entry (ttk.Entry): Entry containing the selected key-file path.
        pasted_keys_text_widget (tk.Text): Text widget for pasted solution keys.
        weights_text_widget (tk.Text): Text widget for question weights.
        test_number_entry (ttk.Entry): Entry for manual test number when using image input.
        input_mode_var (tk.StringVar): Selected grading mode that affects sensitivity.
        status_label (ttk.Label): Status label used for progress/error messages.
        results_text (tk.Text): Results display widget.

    Notes:
        Solution keys are normalized into a temporary file so that downstream
        logic always receives a consistent input format.
    """
    temp_keys_path = None

    try:
        input_path = file_entry.get().strip()
        if not input_path:
            raise ValueError("Input file path is required.")

        pasted_keys_text = pasted_keys_text_widget.get("1.0", tk.END).strip()
        keys_path = keys_entry.get().strip()

        # Prefer pasted solution keys if provided; otherwise load from file.
        # In both cases, normalize the content into a temporary file so the
        # downstream loader sees a consistent format.
        if pasted_keys_text:
            normalized_text = normalize_keys_text(pasted_keys_text)
            with tempfile.NamedTemporaryFile("w", delete=False, suffix=".txt", encoding="utf-8") as f:
                f.write(normalized_text)
                temp_keys_path = f.name
            keys_path = temp_keys_path
        elif keys_path:
            with open(keys_path, "r", encoding="utf-8") as f:
                raw_file_text = f.read()

            normalized_text = normalize_keys_text(raw_file_text)
            with tempfile.NamedTemporaryFile("w", delete=False, suffix=".txt", encoding="utf-8") as f:
                f.write(normalized_text)
                temp_keys_path = f.name
            keys_path = temp_keys_path
        else:
            raise ValueError("Either solution key file path or pasted solution keys are required.")

        weights_text = weights_text_widget.get("1.0", tk.END).strip()
        if not weights_text:
            raise ValueError("Weights field is empty.")

        manual_test_number = None
        if is_image_file(input_path):
            # A single image does not encode ordering context, so the test number
            # must be provided manually.
            test_number_text = test_number_entry.get().strip()
            if not test_number_text:
                raise ValueError("Test number is required for image input.")
            try:
                manual_test_number = int(test_number_text)
            except ValueError:
                raise ValueError("Test number must be an integer.")

        # The direct mode uses a higher color-threshold sensitivity.
        if input_mode_var.get() == "direct":
            color_thr_sensitivity = 4
        else:
            color_thr_sensitivity = 2

        status_label.config(text="Validating weights...", foreground="blue")
        status_label.update_idletasks()

        weights = parse_weights_text(weights_text)
        question_count = expected_question_count(keys_path)

        if len(weights) != question_count:
            raise ValueError(
                f"Number of weights ({len(weights)}) does not match "
                f"the number of questions ({question_count})."
            )

        status_label.config(text="Grading tests... please wait.", foreground="blue")
        status_label.update_idletasks()

        result = grade_tests_with_details(
            input_path,
            keys_path,
            weights,
            manual_test_number,
            color_thr_sensitivity,
        )

        grades = result["grades"]
        tests = result["tests"]

        status_label.config(text="Displaying results...", foreground="blue")
        status_label.update_idletasks()

        results_text.delete("1.0", tk.END)
        for row in grades:
            results_text.insert(tk.END, f"{row[0]} {row[1]}\n")

        status_label.config(text="Creating output files...", foreground="blue")
        status_label.update_idletasks()

        output_dir, pdf_path, txt_path = build_output_paths()

        status_label.config(text="Saving PDF report...", foreground="blue")
        status_label.update_idletasks()
        export_results_pdf(pdf_path, tests)

        status_label.config(text="Saving TXT log...", foreground="blue")
        status_label.update_idletasks()
        export_results_txt(txt_path, tests)

        status_label.config(
            text=f"Grading completed successfully. Files saved in: {output_dir}",
            foreground="green",
        )
        messagebox.showinfo(
            "Success",
            f"Grading completed successfully.\n\n"
            f"Output folder:\n{output_dir}\n\n"
            f"PDF:\n{pdf_path}\n\n"
            f"TXT:\n{txt_path}"
        )

    except Exception:
        status_label.config(text="Failed to grade tests.", foreground="red")
        error_details = traceback.format_exc()
        print(error_details)
        messagebox.showerror("Error", error_details)

    finally:
        if temp_keys_path and os.path.exists(temp_keys_path):
            os.remove(temp_keys_path)


def launch_multi_grade_ui():
    """
    Build and launch the batch grading Tkinter interface.

    The UI allows the user to:
    - choose a PDF or image input file,
    - optionally enter a manual test number for image input,
    - choose or paste solution keys,
    - enter question weights,
    - select the input acquisition mode,
    - run grading,
    - save displayed results.
    """
    root = tk.Tk()
    root.title("Multi Test Grader")
    root.geometry("900x900")

    main_frame = ttk.Frame(root, padding=12)
    main_frame.pack(fill="both", expand=True)

    # Input file selection row.
    file_frame = ttk.Frame(main_frame)
    file_frame.pack(fill="x", pady=(0, 6))

    ttk.Label(file_frame, text="Test sheets file:").pack(side="left")
    file_entry = ttk.Entry(file_frame, width=70)
    file_entry.pack(side="left", padx=(8, 8), fill="x", expand=True)
    file_entry.insert(0, "images/test_sheets.pdf")

    # Manual test number row, used only for single-image grading.
    test_number_frame = ttk.Frame(main_frame)
    test_number_frame.pack(fill="x", pady=(0, 10))

    test_number_label = ttk.Label(test_number_frame, text="Test number:")
    test_number_label.pack(side="left")

    test_number_entry = ttk.Entry(test_number_frame, width=20)
    test_number_entry.pack(side="left", padx=(8, 8))

    ttk.Button(
        file_frame,
        text="Browse...",
        command=lambda: browse_input_file(file_entry, test_number_label, test_number_entry),
    ).pack(side="left")

    # Input acquisition mode affects the color-threshold sensitivity used later.
    input_mode_var = tk.StringVar(value="direct")

    mode_frame = ttk.Frame(main_frame)
    mode_frame.pack(fill="x", pady=(0, 10))

    ttk.Label(mode_frame, text="Input type:").pack(anchor="w")

    ttk.Radiobutton(
        mode_frame,
        text="photo/scans of test sheet directly",
        variable=input_mode_var,
        value="direct",
    ).pack(anchor="w")

    ttk.Radiobutton(
        mode_frame,
        text="Photo of test sheet taken from a monitor or another screen",
        variable=input_mode_var,
        value="screen",
    ).pack(anchor="w")

    # Solution-key file selection row.
    keys_frame = ttk.Frame(main_frame)
    keys_frame.pack(fill="x", pady=(0, 10))

    ttk.Label(keys_frame, text="Solution key file:").pack(side="left")
    keys_entry = ttk.Entry(keys_frame, width=70)
    keys_entry.pack(side="left", padx=(8, 8), fill="x", expand=True)
    keys_entry.insert(0, "solution_keys_for_python.txt")

    ttk.Button(
        keys_frame,
        text="Browse...",
        command=lambda: browse_keys(keys_entry),
    ).pack(side="left")

    # Optional pasted solution-key input area.
    ttk.Label(
        main_frame,
        text="Or paste solution keys content here:",
    ).pack(anchor="w", pady=(10, 6))

    pasted_keys_text = tk.Text(main_frame, height=8, width=100, wrap="word")
    pasted_keys_text.pack(fill="x", expand=False, pady=(0, 10))

    # Question-weight input area.
    ttk.Label(
        main_frame,
        text="Weights list (Python list of numbers):",
    ).pack(anchor="w", pady=(0, 6))

    weights_text = tk.Text(main_frame, height=4, width=100, wrap="word")
    weights_text.pack(fill="x", expand=False, pady=(0, 10))
    weights_text.insert("1.0", "[1, 1, 1, 1, 1]")

    # Status display for progress and error feedback.
    status_label = ttk.Label(main_frame, text="Ready.", foreground="black")
    status_label.pack(anchor="w", pady=(10, 10))

    # Action buttons and results display.
    button_frame = ttk.Frame(main_frame)
    button_frame.pack(fill="x", pady=(0, 10))

    results_text = tk.Text(main_frame, height=20, width=100, wrap="word")

    ttk.Button(
        button_frame,
        text="Grade Tests",
        command=lambda: run_grading(
            file_entry,
            keys_entry,
            pasted_keys_text,
            weights_text,
            test_number_entry,
            input_mode_var,
            status_label,
            results_text,
        ),
    ).pack(side="left")

    ttk.Button(
        button_frame,
        text="Save Results",
        command=lambda: save_results(results_text, status_label),
    ).pack(side="left", padx=(10, 0))

    ttk.Label(main_frame, text="Results:").pack(anchor="w", pady=(10, 6))
    results_text.pack(fill="both", expand=True)

    # Initialize the test-number field state based on the default input path.
    update_test_number_visibility(file_entry, test_number_label, test_number_entry)

    root.mainloop()


if __name__ == "__main__":
    launch_multi_grade_ui()
