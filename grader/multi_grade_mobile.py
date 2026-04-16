"""
Mobile-oriented grading backend for single-image answer-sheet processing.

This module is designed for the Android/Kivy workflow and provides:
- lazy importing of optional heavy dependencies,
- image loading for mobile-supported formats,
- solution-key loading,
- answer-grid extraction from one image,
- detailed grading output for a single test image.

Unlike the desktop batch workflow, this module focuses on image-based grading
for individual tests rather than PDF batches.
"""

import ast
import os


def _require_numpy():
    """
    Import NumPy lazily.

    Returns:
        module: The numpy module.

    Raises:
        ModuleNotFoundError: If NumPy is not available.
    """
    try:
        import numpy as np
        return np
    except ModuleNotFoundError as e:
        raise ModuleNotFoundError(
            "NumPy is required for test image processing but is not available in this build."
        ) from e


def _require_cv2():
    """
    Import OpenCV lazily.

    Returns:
        module: The cv2 module.

    Raises:
        ModuleNotFoundError: If OpenCV is not available.
    """
    try:
        import cv2 as cv
        return cv
    except ModuleNotFoundError as e:
        raise ModuleNotFoundError(
            "OpenCV (cv2) is required for image processing but is not available in this build."
        ) from e


def _require_image_analyzing_functions():
    """
    Import the image-analysis helper module lazily.

    Returns:
        module: image_analyzing_functions module.
    """
    return __import__(
        "image_analyzing_functions",
        fromlist=[
            "light_dark_threshold",
            "current_grey_threshold",
            "current_color_threshold",
            "vector_size",
            "norm_vector",
            "ImageAnalyzer",
        ],
    )


def _require_pattern_extraction_functions():
    """
    Import the pattern-extraction helper module lazily.

    Returns:
        module: pattern_extraction_functions module.
    """
    return __import__(
        "pattern_extraction_functions",
        fromlist=[
            "gr_and_color_of_dark",
            "cone_sweeper",
            "locate_corners",
            "leading_direction",
            "directional_sweeper",
            "locate_marker_pairs",
            "intersect_lines",
            "read_answer_grid",
        ],
    )


def _require_answer_correction_functions():
    """
    Import the answer-correction helper module lazily.

    Returns:
        module: answer_correction_functions module.
    """
    return __import__(
        "answer_correction_functions",
        fromlist=[
            "answer_list_compare",
            "answer_list_grade",
            "total_grade",
            "total_grade_single",
            "detailed_total_grade_single",
            "total_grade_all",
        ],
    )


def load_input_pages(file_path):
    """
    Load the mobile grading input as a single-image list.

    Supported mobile input formats:
    - .jpeg
    - .jpg
    - .png

    Parameters:
        file_path (str): Path to the image file.

    Returns:
        list: A one-item list containing the loaded RGB image.

    Raises:
        ValueError: If the image cannot be read or the format is unsupported.
    """
    cv = _require_cv2()

    ext = os.path.splitext(file_path)[1].lower()

    if ext in [".jpeg", ".jpg", ".png"]:
        img = cv.imread(file_path)
        if img is None:
            raise ValueError(f"Could not read image file: {file_path}")

        # Convert OpenCV BGR output into RGB for downstream consistency.
        img = cv.cvtColor(img, cv.COLOR_BGR2RGB)
        return [img]

    raise ValueError(
        "Unsupported input format for mobile app. Supported formats are: .jpeg, .jpg, .png"
    )


def read_single_test(image, grid_structure, color_thr_sensitivity=2):
    """
    Read one answer-sheet image and extract answer/detection data.

    Parameters:
        image: Input image as a numpy array.
        grid_structure (list[int]): Number of answer choices for each question.
        color_thr_sensitivity (int, optional): Sensitivity factor for color-threshold computation.

    Returns:
        dict: Dictionary containing:
            - answer_matrix
            - detections
            - image_shape
    """
    image_mod = _require_image_analyzing_functions()
    pattern_mod = _require_pattern_extraction_functions()

    ImageAnalyzer = image_mod.ImageAnalyzer
    current_grey_threshold = image_mod.current_grey_threshold
    current_color_threshold = image_mod.current_color_threshold

    gr_and_color_of_dark = pattern_mod.gr_and_color_of_dark
    locate_corners = pattern_mod.locate_corners
    locate_marker_pairs = pattern_mod.locate_marker_pairs
    read_answer_grid = pattern_mod.read_answer_grid

    img = image

    h_markers_number = len(grid_structure)
    w_markers_number = max(grid_structure)

    img_height = img.shape[0]
    img_width = img.shape[1]

    # First pass: estimate image brightness and color baselines.
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

    read_result = read_answer_grid(
        analyzer,
        marker_pairs,
        h_markers_number,
        marker_size,
        grid_structure,
        color_threshold,
    )

    print("Grading the next test ...")
    return {
        "answer_matrix": read_result["answer_matrix"],
        "detections": read_result["detections"],
        "image_shape": [int(img.shape[0]), int(img.shape[1])],
    }


def read_tests(converted_pages, grid_structure, color_thr_sensitivity=2):
    """
    Read one or more mobile input pages and extract answer data for each one.

    Parameters:
        converted_pages (list): Image list, either numpy arrays or convertible image objects.
        grid_structure (list[int]): Number of answer choices for each question.
        color_thr_sensitivity (int, optional): Sensitivity factor for color-threshold computation.

    Returns:
        list[dict]: Per-image answer extraction results.
    """
    np = _require_numpy()

    answer_results = []

    for page in converted_pages:
        if isinstance(page, np.ndarray):
            img = page
        else:
            img = np.array(page)

        answer_results.append(read_single_test(img, grid_structure, color_thr_sensitivity))

    return answer_results


def load_solution_keys(text_file_path):
    """
    Load solution-key data from a normalized text file.

    Supported structures:
    - standard dictionary with 'generated_on' and 'keys'
    - compact dictionary with 'g' and 'k'

    Parameters:
        text_file_path (str): Path to the key file.

    Returns:
        dict: Normalized solution-key dictionary.

    Raises:
        ValueError: If the file contents are malformed.
    """
    with open(text_file_path, "r", encoding="utf-8") as f:
        solution_keys = ast.literal_eval(f.read())

    if not isinstance(solution_keys, dict):
        raise ValueError("Solution key file must contain a dictionary.")

    if "k" in solution_keys:
        solution_keys = {
            "generated_on": solution_keys.get("g", ""),
            "keys": solution_keys["k"],
        }

    if "keys" not in solution_keys:
        raise ValueError("Solution key file is missing the 'keys' field.")

    if "generated_on" not in solution_keys:
        raise ValueError("Solution key file is missing the 'generated_on' field.")

    return solution_keys


def grade_tests(
    image_path,
    text_file_path,
    weights,
    manual_test_number=None,
    color_thr_sensitivity=4,
):
    """
    Grade one or more mobile input images and return structured result dictionaries.

    Parameters:
        image_path (str): Path to the test image.
        text_file_path (str): Path to the normalized solution-key file.
        weights (list[int | float]): Per-question weights.
        manual_test_number (int, optional): Test number to assign to the image.
        color_thr_sensitivity (int, optional): Sensitivity factor for color-threshold computation.

    Returns:
        list[dict]: Structured grading results for the processed image(s).
    """
    correction_mod = _require_answer_correction_functions()
    detailed_total_grade_single = correction_mod.detailed_total_grade_single

    loaded_pages = load_input_pages(image_path)
    solution_keys = load_solution_keys(text_file_path)
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

        answer_result = answers[i]
        answer_grid = answer_result["answer_matrix"]
        detections = answer_result.get("detections", [])
        image_shape = answer_result.get("image_shape", [])
        matched = False

        # Find the solution-key group assigned to this test number.
        for j in range(len(keys)):
            exam_numbers = keys[j][0]
            current_solutions = keys[j][1]

            if test_number in exam_numbers:
                detailed = detailed_total_grade_single(answer_grid, current_solutions, weights)
                grade = detailed["total_grade"]

                grades.append({
                    "test_number": test_number,
                    "grade": grade,
                    "questions": detailed["questions"],
                    "student_answers": answer_grid,
                    "matched_solution_exam_numbers": exam_numbers,
                    "status": "ok",
                    "left_text": f"test number {test_number}",
                    "right_text": f"has grade {grade}",
                    "display_text": f"test number {test_number} has grade {grade}",
                    "detections": detections,
                    "image_shape": image_shape,
                    "image_path": image_path,
                })
                matched = True
                break

        if not matched:
            grades.append({
                "test_number": test_number,
                "grade": None,
                "questions": [],
                "student_answers": answer_grid,
                "matched_solution_exam_numbers": [],
                "status": "no_matching_solution_key",
                "left_text": f"test number {test_number}",
                "right_text": "has no matching solution key",
                "display_text": f"test number {test_number} has no matching solution key",
                "detections": detections,
                "image_shape": image_shape,
                "image_path": image_path,
            })

    return grades
