"""
Pattern-extraction helpers for detecting sheet structure and answer boxes.

This module contains the geometric/image-processing routines used to:
- estimate dark reference values,
- locate corner markers,
- sweep along directions to find marker transitions,
- determine marker pairs and answer-grid geometry.

These functions build on the lower-level ImageAnalyzer utilities.
"""

import math
import numpy as np

from image_analyzing_functions import (
    light_dark_threshold,
    current_grey_threshold,
    current_color_threshold,
    vector_size,
    norm_vector,
    ImageAnalyzer,
)


def gr_and_color_of_dark(analyzer, testing_sqr_size):
    """
    Estimate the darkest grey level and darkest color in a sampling region.

    The search begins in the lower-right area of the page, where the large dark
    reference square is expected, and samples square regions of the given size.

    Parameters:
        analyzer (ImageAnalyzer): Image analyzer instance.
        testing_sqr_size (int): Side length of the sampled square region.

    Returns:
        tuple[float, list[float]]:
            - darkest sampled grey value
            - darkest sampled average RGB color
    """
    current_grey = 255
    current_color = [255, 255, 255]
    start_point = [7 * analyzer.image_height // 16, 7 * analyzer.image_width // 8]

    h_jumps = round(analyzer.image_height / (8 * testing_sqr_size))
    w_jumps = round(analyzer.image_width / (8 * testing_sqr_size))

    for i in range(h_jumps):
        for j in range(w_jumps):
            test_point = [
                start_point[0] + i * testing_sqr_size,
                start_point[1] + j * testing_sqr_size,
            ]

            test_grey = analyzer.avg_grey_sqr(testing_sqr_size, test_point)
            test_color = analyzer.average_color_sqr(testing_sqr_size, test_point)

            if test_grey <= current_grey:
                current_grey = test_grey

            if min(test_color) <= min(current_color):
                current_color = test_color

    return current_grey, current_color


def darkest_point(analyzer, step_size, square_center):
    """
    Find the darkest pixel within a square neighborhood around a center point.

    Parameters:
        analyzer (ImageAnalyzer): Image analyzer instance.
        step_size (int): Neighborhood side length.
        square_center (list[int] | tuple[int, int]): Center point of the search region.

    Returns:
        list[int] | tuple[int, int]: Coordinates of the darkest detected point.
    """
    dark_point = square_center

    if step_size == 1:
        return dark_point

    for h in range(step_size):
        for w in range(step_size):
            at_point = [
                square_center[0] + h - step_size // 2,
                square_center[1] + w - step_size // 2,
            ]

            if analyzer.gr_value(at_point) <= analyzer.gr_value(dark_point):
                dark_point = at_point

    return dark_point


def cone_sweeper(analyzer, start_point, step_size, direction, counter_border, grey_threshold=None):
    """
    Sweep outward from a corner in a cone-like pattern until a dark region is found.

    Parameters:
        analyzer (ImageAnalyzer): Image analyzer instance.
        start_point (list[int]): Starting point for the sweep.
        step_size (int): Sweep step size.
        direction (list[int] | tuple[int, int]): Sweep orientation vector.
        counter_border (int): Maximum sweep extent.
        grey_threshold (float, optional): Override grey threshold.

    Returns:
        list[int] | tuple[int, int]: Darkest point found near the first detected dark region.

    Raises:
        ValueError: If the sweep goes out of image bounds or no dark square is found.
    """
    a = direction[0]
    b = direction[1]

    for i in range(counter_border):
        for j in range(i + 1):
            test_point = [
                start_point[0] - b * step_size * (i - j),
                start_point[1] + a * step_size * j,
            ]

            if not (
                0 <= test_point[0] < analyzer.image_height
                and 0 <= test_point[1] < analyzer.image_width
            ):
                raise ValueError(f"Sweeper went out of image bounds at point {test_point}.")

            if analyzer.is_square_dark(step_size, test_point, grey_threshold):
                return darkest_point(analyzer, 2 * step_size, test_point)

    raise ValueError("No dark square found during cone sweep.")


def locate_corners(analyzer, step_size, counter_border, grey_threshold=None):
    """
    Locate the four main corner markers of the answer sheet.

    The search is performed from the four image corners using cone sweeps.

    Parameters:
        analyzer (ImageAnalyzer): Image analyzer instance.
        step_size (int): Sweep step size.
        counter_border (int): Maximum sweep extent.
        grey_threshold (float, optional): Override grey threshold.

    Returns:
        tuple[list[int], list[int], list[int], list[int]]:
            Corner centers in the order:
            - origin (upper-left reference)
            - lower-left
            - upper-right
            - lower-right
    """
    corners_data = [
        ([step_size, step_size], [1, -1]),
        ([analyzer.image_height - step_size, step_size], [1, 1]),
        ([step_size, analyzer.image_width - step_size], [-1, -1]),
        ([analyzer.image_height - step_size, analyzer.image_width - step_size], [-1, 1]),
    ]

    corners = []

    for start_point, direction in corners_data:
        dark_point = cone_sweeper(
            analyzer, start_point, step_size, direction, counter_border, grey_threshold
        )
        corners.append(analyzer.find_center(dark_point, grey_threshold))

    return tuple(corners)


def leading_direction(orgn, dl_crnr, ur_crnr, dr_crnr):
    """
    Compute the main height and width directions of the sheet grid.

    The directions are estimated from the four corner markers.

    Parameters:
        orgn (list[int]): Origin corner.
        dl_crnr (list[int]): Lower-left corner.
        ur_crnr (list[int]): Upper-right corner.
        dr_crnr (list[int]): Lower-right corner.

    Returns:
        tuple[list[list[float]], list[list[float]]]:
            - two height-direction unit vectors
            - two width-direction unit vectors
    """
    height_directions = [
        norm_vector([dl_crnr[0] - orgn[0], dl_crnr[1] - orgn[1]]),
        norm_vector([dr_crnr[0] - ur_crnr[0], dr_crnr[1] - ur_crnr[1]]),
    ]

    width_directions = [
        norm_vector([ur_crnr[0] - orgn[0], ur_crnr[1] - orgn[1]]),
        norm_vector([dr_crnr[0] - dl_crnr[0], dr_crnr[1] - dl_crnr[1]]),
    ]

    return height_directions, width_directions


def directional_sweeper(analyzer, counter_border, start_point, step_size, vector, grey_threshold=None):
    """
    Sweep along a direction until a dark/light transition is detected.

    Parameters:
        analyzer (ImageAnalyzer): Image analyzer instance.
        counter_border (int): Maximum sweep distance.
        start_point (list[int]): Starting point.
        step_size (int): Sweep step size.
        vector (list[float] | tuple[float, float]): Sweep direction vector.
        grey_threshold (float, optional): Override grey threshold.

    Returns:
        list[int] | None: First point where the dark/light state changes.

    Raises:
        ValueError: If the sweep exits the image bounds.
    """
    initial_gradient = analyzer.is_square_dark(step_size, start_point, grey_threshold)

    for i in range(counter_border - step_size):
        moved = [
            round(start_point[0] + i * step_size * vector[0]),
            round(start_point[1] + i * step_size * vector[1]),
        ]

        if not (0 <= moved[0] < analyzer.image_height and 0 <= moved[1] < analyzer.image_width):
            raise ValueError(f"Directional sweeper went out of bounds at point {moved}.")

        if analyzer.is_square_dark(step_size, moved, grey_threshold) != initial_gradient:
            return moved

    return None


def locate_marker_pairs(
    analyzer,
    counter_border,
    origin,
    origin_height,
    origin_width,
    ur_corner,
    dl_corner,
    dr_corner,
    h_mrkrs_nmbr,
    w_mrkrs_nmbr,
    grey_threshold=None,
):
    """
    Locate pairs of border markers along the sheet height and width directions.

    Parameters:
        analyzer (ImageAnalyzer): Image analyzer instance.
        counter_border (int): Maximum sweep distance.
        origin (list[int]): Origin marker center.
        origin_height (int): Estimated origin-marker height.
        origin_width (int): Estimated origin-marker width.
        ur_corner (list[int]): Upper-right corner marker.
        dl_corner (list[int]): Lower-left corner marker.
        dr_corner (list[int]): Lower-right corner marker.
        h_mrkrs_nmbr (int): Number of height markers to locate.
        w_mrkrs_nmbr (int): Number of width markers to locate.
        grey_threshold (float, optional): Override grey threshold.

    Returns:
        list[list[list]]: Marker pairs for height and width directions.

    Raises:
        ValueError: If a zero direction vector is encountered or if expected
            marker transitions cannot be found.
    """
    # Step sizes used to advance from one marker position to the next.
    h_step = origin_height // 4
    w_step = origin_width // 2

    mrkr_pairs = [[], []]
    markers_numbers = [h_mrkrs_nmbr, w_mrkrs_nmbr]
    step = [h_step, w_step]

    # Starting and target corner pairs for height- and width-marker sweeps.
    start_pairs = [[origin, ur_corner], [origin, dl_corner]]
    end_pairs = [[dl_corner, dr_corner], [ur_corner, dr_corner]]

    for i in range(2):
        for j in range(markers_numbers[i]):
            # Make a shallow copy of the current start pair so both points can be
            # updated independently for this marker pair.
            marker_center = [start_pairs[i][0][:], start_pairs[i][1][:]]

            # Reserve a slot for the current pair.
            mrkr_pairs[i].append([])

            for k in range(2):
                direction = [
                    end_pairs[i][k][0] - marker_center[k][0],
                    end_pairs[i][k][1] - marker_center[k][1]
                ]

                # Guard against a zero direction vector.
                if vector_size(direction) == 0:
                    raise ValueError(
                        f"Zero direction vector in locate_marker_pairs for "
                        f"i={i}, j={j}, k={k}. Current point {marker_center[k]} "
                        f"is equal to target point {end_pairs[i][k]}."
                    )

                direction_normed = norm_vector(direction)

                exited = directional_sweeper(
                    analyzer,
                    counter_border,
                    marker_center[k],
                    1,
                    direction_normed,
                    grey_threshold,
                )

                if exited is None:
                    raise ValueError(
                        f"Could not find marker exit for i={i}, j={j}, k={k}, "
                        f"start_point={marker_center[k]}, direction={direction_normed}."
                    )

                # Move past the detected edge before searching for the next marker.
                shift_exited = [
                    round(exited[0] + step[i] * direction_normed[0]),
                    round(exited[1] + step[i] * direction_normed[1])
                ]

                if not (
                    0 <= shift_exited[0] < analyzer.image_height
                    and 0 <= shift_exited[1] < analyzer.image_width
                ):
                    raise ValueError(
                        f"Shifted exit point out of bounds for i={i}, j={j}, k={k}: "
                        f"{shift_exited}."
                    )

                found = directional_sweeper(
                    analyzer,
                    counter_border,
                    shift_exited,
                    step[i],
                    direction_normed,
                    grey_threshold,
                )

                if found is None:
                    raise ValueError(
                        f"Could not find next marker for i={i}, j={j}, k={k}, "
                        f"start_point={shift_exited}, step_size={step[i]}, "
                        f"direction={direction_normed}."
                    )

                in_box = darkest_point(analyzer, step[i], found)

                # find_center(in_box) returns one point [row, col]. Keep the
                # pair structure intact by updating only the current point.
                new_center = analyzer.find_center(in_box, grey_threshold)

                if not (
                    isinstance(new_center, (list, tuple))
                    and len(new_center) == 2
                ):
                    raise ValueError(
                        f"Invalid marker center returned for i={i}, j={j}, k={k}: "
                        f"{new_center}."
                    )

                new_center = list(new_center)

                mrkr_pairs[i][-1].append(new_center)

                # Update both the local working pair and the global start pair
                # so the next sweep starts from the newly found center.
                marker_center[k] = new_center
                start_pairs[i][k] = new_center

    return mrkr_pairs


def intersect_lines(H, W):
    """
    Compute the intersection point of two lines defined by point pairs.

    Parameters:
        H (list[list[int]]): First line defined by two points.
        W (list[list[int]]): Second line defined by two points.

    Returns:
        list[int]: Intersection point as [row, col].

    Raises:
        ValueError: If the two lines are parallel or coincident.
    """
    (h1, w1), (h2, w2) = H
    (h3, w3), (h4, w4) = W

    x1, y1 = w1, h1
    x2, y2 = w2, h2
    x3, y3 = w3, h3
    x4, y4 = w4, h4

    A1 = y2 - y1
    B1 = x1 - x2
    C1 = A1 * x1 + B1 * y1

    A2 = y4 - y3
    B2 = x3 - x4
    C2 = A2 * x3 + B2 * y3

    det = A1 * B2 - A2 * B1
    if det == 0:
        raise ValueError("Lines are parallel or coincident.")

    x = (C1 * B2 - C2 * B1) / det
    y = (A1 * C2 - A2 * C1) / det

    return [int(y), int(x)]


def read_answer_grid(
    analyzer,
    mrker_pairs,
    h_mrkrs_number,
    mrkr_size,
    grd_strctr,
    color_threshold=None,
):
    """
    Read the answer grid defined by the located marker pairs.

    For each question/choice intersection:
    - estimate the box center,
    - determine whether the box is filled,
    - store the binary answer matrix,
    - store detailed detection metadata.

    Parameters:
        analyzer (ImageAnalyzer): Image analyzer instance.
        mrker_pairs (list): Marker pairs for height and width directions.
        h_mrkrs_number (int): Number of question rows.
        mrkr_size (int): Estimated marker size used to size answer-box checks.
        grd_strctr (list[int]): Number of answer choices for each question.
        color_threshold (list[float], optional): Override color threshold.

    Returns:
        dict: Dictionary containing:
            - answer_matrix: extracted binary answer grid
            - detections: per-box detection metadata
    """
    test_box_size = mrkr_size
    answer_matrix = []
    detections = []

    for q in range(h_mrkrs_number):
        answer_matrix.append([])

        for c in range(grd_strctr[q]):
            answer_box_center = intersect_lines(mrker_pairs[0][q], mrker_pairs[1][c])
            filled = analyzer.is_square_colored(
                test_box_size // 2,
                answer_box_center,
                color_threshold,
            ) is True

            if filled:
                answer_matrix[q].append(1)
            else:
                answer_matrix[q].append(0)

            detections.append({
                "question_number": q + 1,
                "choice_index": c,
                "center": answer_box_center,
                "filled": filled,
            })

    return {
        "answer_matrix": answer_matrix,
        "detections": detections,
    }
