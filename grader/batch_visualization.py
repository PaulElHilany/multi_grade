"""
Visualization helpers for batch-grading reports.

This module draws simple grading overlays on test-sheet images so the exported
PDF report can show how the software interpreted detected answer boxes.
"""

import cv2 as cv


def draw_overlay(image, questions):
    """
    Draw visual markers on a test-sheet image for detected answer boxes.

    For each detected answer box:
    - a white dot marks a box interpreted as filled
    - a red dot marks a box interpreted as not filled

    Parameters:
        image (numpy.ndarray): Source image of the test sheet.
        questions (list[dict]): Per-question data containing box coordinates
            and detection states.

    Returns:
        numpy.ndarray: Annotated copy of the input image.
    """
    output = image.copy()

    for q in questions:
        for box in q["boxes"]:
            # Use stored center coordinates when available; otherwise derive them
            # from the box geometry.
            cx = int(box.get("center_x", box["x"] + box["w"] / 2))
            cy = int(box.get("center_y", box["y"] + box["h"] / 2))

            # Shift the marker slightly upward so it is easier to see.
            dot_y = max(5, cy - 6)

            color = (255, 255, 255) if box["is_filled"] else (0, 0, 255)

            cv.circle(output, (cx, dot_y), 6, color, -1)
            cv.circle(output, (cx, dot_y), 6, (0, 0, 0), 1)

    return output
