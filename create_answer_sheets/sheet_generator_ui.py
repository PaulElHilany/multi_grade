"""
Tkinter UI for generating multiple-choice answer sheets and solution-key files.

This module provides a desktop interface for:
- entering the exam solution structure,
- choosing the number of answer sheets to generate,
- optionally selecting the pdflatex executable,
- choosing whether all test numbers should use the same solution key,
- generating the answer-sheet PDF and the corresponding solution-key outputs.

Generated outputs are written into a timestamped folder so that each run is kept separate.
"""

import ast
import os
from datetime import datetime
import tkinter as tk
from tkinter import ttk, messagebox, filedialog

# Import the PDF-generation function used to create numbered answer sheets.
from create_answer_sheets import exams_pdf

# Import the function that creates the text, PDF, and QR-code key outputs.
from create_solution_keys import save_print_keys_outputs


def parse_solutions_text(text):
    """
    Parse and validate the solutions text entered in the UI.

    The expected format is a Python list of lists containing only 0 and 1 values.
    Each inner list represents one question, where 1 marks a correct choice and
    0 marks an incorrect choice.

    Parameters:
        text (str): Raw text entered by the user.

    Returns:
        list[list[int]]: Parsed and validated solutions structure.

    Raises:
        ValueError: If the text is not valid Python literal syntax, is not a
            list of lists, contains more than 30 questions, or includes values
            other than 0 and 1.
    """
    try:
        # Safely parse the text as a Python literal without using eval().
        value = ast.literal_eval(text)
    except Exception as e:
        raise ValueError(f"Invalid solutions format: {e}")

    if not isinstance(value, list):
        raise ValueError("Solutions must be a list of lists.")

    # The current UI/manual supports at most 30 questions.
    if len(value) > 30:
        raise ValueError("Solutions list cannot contain more than 30 items.")

    for i, row in enumerate(value):
        if not isinstance(row, list):
            raise ValueError(f"Item {i} is not a list.")
        for j, item in enumerate(row):
            if item not in (0, 1):
                raise ValueError(
                    f"Invalid value at solutions[{i}][{j}]: {item}. Only 0 and 1 are allowed."
                )

    return value


def generate_answer_sheets(
    solutions_text_widget,
    sheets_entry,
    pdflatex_entry,
    same_key_var,
    status_label,
):
    """
    Read user input from the UI, validate it, and generate output files.

    This function:
    - reads the solution structure from the text widget,
    - reads the requested number of sheets,
    - gets the pdflatex path,
    - checks whether one shared key or multiple key variants should be used,
    - creates a timestamped output folder,
    - generates the answer-sheet PDF,
    - generates the solution-key PDF, TXT, and QR outputs.

    Parameters:
        solutions_text_widget (tk.Text): Text widget containing the solution lists.
        sheets_entry (ttk.Entry): Entry widget for the number of sheets.
        pdflatex_entry (ttk.Entry): Entry widget for the pdflatex executable path.
        same_key_var (tk.BooleanVar): Checkbox state indicating whether all tests
            should use the same solution key.
        status_label (ttk.Label): Label used to display progress/status messages.

    Raises:
        ValueError: If the user input is missing or invalid.
        Exception: Propagates unexpected errors from file generation routines.
    """
    try:
        solutions_text = solutions_text_widget.get("1.0", tk.END).strip()
        if not solutions_text:
            raise ValueError("Solutions field is empty.")

        solutions = parse_solutions_text(solutions_text)

        sheets_text = sheets_entry.get().strip()
        if not sheets_text:
            raise ValueError("Number of sheets is required.")

        number_of_sheets = int(sheets_text)
        if number_of_sheets <= 0:
            raise ValueError("Number of sheets must be a positive integer.")

        pdflatex_path = pdflatex_entry.get().strip()
        if not pdflatex_path:
            # Fall back to the system command if no explicit path is provided.
            pdflatex_path = "pdflatex"

        use_same_key_for_all = same_key_var.get()

        # Create one shared timestamp so all outputs from the same run are grouped together.
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_dir = f"generated_test_{timestamp}"
        os.makedirs(output_dir, exist_ok=True)

        status_label.config(text="Generating files...", foreground="blue")
        status_label.update_idletasks()

        # Generate the numbered answer-sheet PDF.
        pdf_path = exams_pdf(
            solutions,
            number_of_sheets=number_of_sheets,
            output_dir=output_dir,
            pdflatex_path=pdflatex_path,
            timestamp=timestamp,
        )

        # Generate the solution-key outputs used for grading and reference.
        key_pdf_path, key_txt_path, key_qr_path = save_print_keys_outputs(
            number_of_sheets,
            solutions,
            output_dir=output_dir,
            timestamp=timestamp,
            same_key_for_all=use_same_key_for_all,
        )

        status_label.config(
            text="Files created successfully.",
            foreground="green",
        )

        key_mode_text = (
            "Same solution key used for all test numbers."
            if use_same_key_for_all
            else "Multiple solution-key variants used."
        )

        messagebox.showinfo(
            "Success",
            "Files created successfully:\n\n"
            f"{key_mode_text}\n\n"
            f"Output folder:\n{output_dir}\n\n"
            f"Answer-sheet PDF:\n{pdf_path}\n\n"
            f"Solution-key PDF:\n{key_pdf_path}\n\n"
            f"Solution-key TXT:\n{key_txt_path}\n\n"
            f"Solution-key QR:\n{key_qr_path}",
        )

    except Exception as e:
        status_label.config(text="Failed to generate files.", foreground="red")
        messagebox.showerror("Error", str(e))


def browse_pdflatex(pdflatex_entry):
    """
    Open a file dialog so the user can select the pdflatex executable.

    This is mainly useful on Windows systems where pdflatex may not be
    available directly on the system PATH.

    Parameters:
        pdflatex_entry (ttk.Entry): Entry widget to update with the selected path.
    """
    file_path = filedialog.askopenfilename(
        title="Select pdflatex executable",
        filetypes=[("Executable files", "*.exe"), ("All files", "*.*")],
    )
    if file_path:
        pdflatex_entry.delete(0, tk.END)
        pdflatex_entry.insert(0, file_path)


def launch_answer_sheet_ui():
    """
    Build and launch the answer-sheet generator Tkinter interface.

    The UI allows the user to:
    - enter a list-of-lists solution structure,
    - set the number of answer sheets to create,
    - specify the pdflatex executable,
    - choose whether one shared key should be used for all tests,
    - generate output files with one button click.
    """
    root = tk.Tk()
    root.title("Answer Sheet PDF Generator")
    root.geometry("850x700")

    main_frame = ttk.Frame(root, padding=12)
    main_frame.pack(fill="both", expand=True)

    ttk.Label(
        main_frame,
        text="Solutions list (Python list of lists with 0/1 values, max 30 items):",
    ).pack(anchor="w", pady=(0, 6))

    # Multi-line input box for entering the exam answer structure.
    solutions_text = tk.Text(main_frame, height=18, width=100, wrap="word")
    solutions_text.pack(fill="both", expand=False, pady=(0, 10))

    # Provide a default example so the expected format is immediately visible.
    solutions_text.insert(
        "1.0",
        """[
    [0, 1, 0],
    [1, 0],
    [1, 1, 0, 0],
    [1, 0, 0, 0, 0, 1, 0],
    [1, 1, 1, 1],
    [0, 0, 0, 1],
    [0, 1, 0, 1, 0],
    [1, 0],
    [1, 1, 0, 0, 1, 0, 0, 0],
    [1, 1, 1, 1, 1],
    [0, 0, 0, 1, 0, 0, 1, 0],
    [1, 0],
    [1, 1, 0]
]""",
    )

    sheets_frame = ttk.Frame(main_frame)
    sheets_frame.pack(fill="x", pady=(0, 10))

    ttk.Label(sheets_frame, text="Number of sheets:").pack(side="left")
    sheets_entry = ttk.Entry(sheets_frame, width=10)
    sheets_entry.pack(side="left", padx=(8, 20))
    sheets_entry.insert(0, "5")

    pdflatex_frame = ttk.Frame(main_frame)
    pdflatex_frame.pack(fill="x", pady=(0, 10))

    ttk.Label(pdflatex_frame, text="pdflatex path:").pack(side="left")
    pdflatex_entry = ttk.Entry(pdflatex_frame, width=60)
    pdflatex_entry.pack(side="left", padx=(8, 8), fill="x", expand=True)
    pdflatex_entry.insert(0, "pdflatex")

    ttk.Button(
        pdflatex_frame,
        text="Browse...",
        command=lambda: browse_pdflatex(pdflatex_entry),
    ).pack(side="left")

    # Option to disable shuffling and use one identical key for every test number.
    same_key_var = tk.BooleanVar(value=False)
    ttk.Checkbutton(
        main_frame,
        text="Use the same solution key for all test numbers",
        variable=same_key_var,
    ).pack(anchor="w", pady=(0, 10))

    status_label = ttk.Label(main_frame, text="Ready.", foreground="black")
    status_label.pack(anchor="w", pady=(10, 10))

    ttk.Button(
        main_frame,
        text="Generate test sheets and solution keys",
        command=lambda: generate_answer_sheets(
            solutions_text,
            sheets_entry,
            pdflatex_entry,
            same_key_var,
            status_label,
        ),
    ).pack(pady=(0, 10))

    root.mainloop()


if __name__ == "__main__":
    launch_answer_sheet_ui()
