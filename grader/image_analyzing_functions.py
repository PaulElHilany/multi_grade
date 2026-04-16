"""
Low-level image analysis helpers for MultiGrade.

This module provides:
- adaptive grey/color threshold helpers,
- basic vector utilities,
- grayscale luminance computation,
- an ImageAnalyzer class for querying pixel and small-region properties.

These helpers are used by the pattern-extraction logic to detect markers,
corners, and answer boxes in scanned or photographed answer sheets.
"""

import math
import numpy as np


# Sensitivity parameter used to derive the grey threshold.
# This acts as the inverse of sensitivity and must be in ]1, +infinity[:
# - values closer to 1 make the threshold less aggressive
# - values farther from 1 make detection more sensitive
grey_thr_sensitivity = 3 / 2

# Sensitivity parameter used to derive the color threshold.
# Recommended values:
# - 4 for photos/scans taken from paper
# - 2 for photos taken from a screen
color_thr_sensitivity = 2


def light_dark_threshold(dark, light, s):
    """
    Compute a threshold between a dark reference value and a light reference value.

    Parameter s is the dark-sensitivity coefficient:
    the smaller s is, the closer the threshold moves toward the dark value.

    Parameters:
        dark (float): Reference value for a dark region.
        light (float): Reference value for a light region.
        s (float): Sensitivity coefficient.

    Returns:
        float: Interpolated threshold value.
    """
    return (1 / s) * dark + (1 - (1 / s)) * light


def current_grey_threshold(dark, light):
    """
    Compute the current grey threshold using the configured grey sensitivity.

    Parameters:
        dark (float): Reference dark grey level.
        light (float): Reference light grey level.

    Returns:
        float: Grey threshold.
    """
    return light_dark_threshold(dark, light, grey_thr_sensitivity)


def current_color_threshold(dark, light, sensitivity=None):
    """
    Compute the current color threshold using the configured color sensitivity.

    Parameters:
        dark (float): Reference dark channel value.
        light (float): Reference light/background channel value.
        sensitivity (float, optional): Override sensitivity value.

    Returns:
        float: Color threshold.
    """
    if sensitivity is None:
        sensitivity = color_thr_sensitivity
    return light_dark_threshold(dark, light, sensitivity)


def vector_size(coords):
    """
    Compute the Euclidean norm of a 2D vector.

    Parameters:
        coords (list[float] | tuple[float, float]): 2D vector.

    Returns:
        float: Vector length.
    """
    return math.sqrt(coords[0] * coords[0] + coords[1] * coords[1])


def norm_vector(coords):
    """
    Return the normalized version of a 2D vector.

    Parameters:
        coords (list[float] | tuple[float, float]): 2D vector.

    Returns:
        list[float]: Unit vector in the same direction.
    """
    return [coords[0] / vector_size(coords), coords[1] / vector_size(coords)]


def luminance(channel):
    """
    Compute the grayscale luminance of an RGB color triplet.

    The weights correspond to the standard perceptual luminance formula,
    giving more importance to green and less to blue.

    Parameters:
        channel (list[float] | tuple[float, float, float]): RGB values.

    Returns:
        float: Grayscale luminance.
    """
    grey_lum = 0.299 * channel[0] + 0.587 * channel[1] + 0.114 * channel[2]
    return grey_lum


class ImageAnalyzer:
    """
    Helper class for analyzing an image using grey and color thresholds.

    Attributes:
        image: Image pixel matrix.
        image_height (int): Image height in pixels.
        image_width (int): Image width in pixels.
        grey_threshold (float): Threshold used for dark/light detection.
        color_threshold (list[float]): RGB threshold used for colored-region detection.
    """

    def __init__(self, image, grey_threshold, color_threshold):
        """
        Initialize the analyzer.

        Parameters:
            image: Pixel matrix.
            grey_threshold (float): Threshold used for dark/light references.
            color_threshold (list[float]): RGB threshold used to detect colored regions.
        """
        self.image = image
        self.image_height = len(image)
        self.image_width = len(image[0])
        self.grey_threshold = grey_threshold
        self.color_threshold = color_threshold

    def gr_value(self, point):
        """
        Return the grayscale intensity of a single pixel.

        Parameters:
            point (list[int] | tuple[int, int]): Pixel coordinates [row, col].

        Returns:
            float: Pixel luminance.
        """
        pixel = list(self.image[point[0], point[1]])
        return float(luminance(pixel))

    def light_grey_representative(self, average_grey):
        """
        Find a sampled pixel whose grey value is at least the average grey.

        This serves as a representative "light" point in the image.

        Parameters:
            average_grey (float): Average grey level of the image.

        Returns:
            list[int] | None: Coordinates of a representative light point, if found.
        """
        part_height = int(self.image_height / 5)
        part_width = int(self.image_width / 5)
        test_point = [0, 0]

        for h in range(part_height - 1):
            for w in range(part_width - 1):
                test_point = [5 * h, 5 * w]

                if self.gr_value(test_point) >= average_grey:
                    return test_point

        return None

    def avg_grey_and_color(self):
        """
        Compute approximate average grey level and average RGB color of the image.

        The image is sampled every 5 pixels in both directions to reduce cost.

        Returns:
            tuple[float, list[float]]:
                - approximate average grey level
                - approximate average RGB color
        """
        part_height = self.image_height // 5 - 1
        part_width = self.image_width // 5 - 1
        grey_sum = 0
        color_sum = [0, 0, 0]

        for h in range(part_height):
            for w in range(part_width):
                grey_sum += self.gr_value([5 * h, 5 * w])

                for i in range(3):
                    color_sum[i] += self.image[5 * h, 5 * w][i]

        average_grey = grey_sum / (part_height * part_width)
        average_color = [color_sum[i] / (part_height * part_width) for i in range(3)]

        return average_grey, average_color

    def average_color_sqr(self, sqr_size, ctr_point):
        """
        Compute the average RGB color inside a square centered at ctr_point.

        If sqr_size == 1, the center pixel color is returned directly.

        Parameters:
            sqr_size (int): Side length of the square region.
            ctr_point (list[int] | tuple[int, int]): Center point of the square.

        Returns:
            list[float]: Average RGB color.
        """
        if sqr_size == 1:
            return self.image[ctr_point[0], ctr_point[1]]

        color_sum = [0, 0, 0]
        half_size = sqr_size // 2

        for h in range(sqr_size):
            for w in range(sqr_size):
                for i in range(3):
                    color_sum[i] += self.image[
                        ctr_point[0] - half_size + h,
                        ctr_point[1] - half_size + w
                    ][i]

        average = [color_sum[i] / (sqr_size * sqr_size) for i in range(3)]
        return average

    def avg_grey_sqr(self, sqr_size, ctr_point):
        """
        Compute the average grayscale value of a square centered at ctr_point.

        This is done by first averaging the square color, then converting to grey.

        Parameters:
            sqr_size (int): Side length of the square region.
            ctr_point (list[int] | tuple[int, int]): Center point of the square.

        Returns:
            float: Average grayscale luminance.
        """
        avg_color = self.average_color_sqr(sqr_size, ctr_point)
        return float(luminance(avg_color))

    def is_square_dark(self, sqr_size, crt_point, grey_threshold=None):
        """
        Check whether a square region is considered dark.

        Parameters:
            sqr_size (int): Side length of the square region.
            crt_point (list[int] | tuple[int, int]): Center point of the square.
            grey_threshold (float, optional): Override grey threshold.

        Returns:
            bool: True if the average grey value is at or below the threshold.
        """
        if grey_threshold is None:
            grey_threshold = self.grey_threshold
        return bool(self.avg_grey_sqr(sqr_size, crt_point) <= grey_threshold)

    def is_colored(self, pixel_color, color_threshold=None):
        """
        Check whether a pixel color is considered colored.

        A pixel is considered colored if at least one RGB channel is at or below
        its corresponding threshold.

        Parameters:
            pixel_color (list[float] | tuple[float, float, float]): RGB value.
            color_threshold (list[float], optional): Override RGB threshold.

        Returns:
            bool: True if the color is classified as colored.
        """
        if color_threshold is None:
            color_threshold = self.color_threshold

        return bool(
            pixel_color[0] <= color_threshold[0]
            or pixel_color[1] <= color_threshold[1]
            or pixel_color[2] <= color_threshold[2]
        )

    def is_square_colored(self, sqr_size, ctr_point, color_threshold=None):
        """
        Check whether the average color of a square region is considered colored.

        Parameters:
            sqr_size (int): Side length of the square region.
            ctr_point (list[int] | tuple[int, int]): Center point of the square.
            color_threshold (list[float], optional): Override RGB threshold.

        Returns:
            bool: True if the region is classified as colored.
        """
        if color_threshold is None:
            color_threshold = self.color_threshold

        avg_color_sqr = self.average_color_sqr(sqr_size, ctr_point)
        return self.is_colored(avg_color_sqr, color_threshold)

    def is_dark(self, point, grey_threshold=None):
        """
        Check whether a pixel is dark according to the grey threshold.

        Parameters:
            point (list[int] | tuple[int, int]): Pixel coordinates [row, col].
            grey_threshold (float, optional): Override grey threshold.

        Returns:
            bool: True if the pixel luminance is at or below the threshold.
        """
        if grey_threshold is None:
            grey_threshold = self.grey_threshold
        return bool(self.gr_value(point) <= grey_threshold)

    def center_height_width(self, point, grey_threshold=None):
        """
        Estimate the center, height, and width of a connected dark smudge.

        Starting from a dark point, this method expands along the four main
        directions:
        - up
        - down
        - left
        - right

        It then estimates the bounding dimensions and approximate center.

        Parameters:
            point (list[int] | tuple[int, int]): Starting dark pixel.
            grey_threshold (float, optional): Override grey threshold.

        Returns:
            list: [center, height, width]
        """
        if grey_threshold is None:
            grey_threshold = self.grey_threshold

        u = 0
        d = 0
        l = 0
        r = 0

        # Count consecutive dark pixels upward from the starting point.
        while self.is_dark([point[0] - u, point[1]], grey_threshold):
            u += 1

        # Count consecutive dark pixels downward from the starting point.
        while self.is_dark([point[0] + d, point[1]], grey_threshold):
            d += 1

        # Count consecutive dark pixels to the left from the starting point.
        while self.is_dark([point[0], point[1] - l], grey_threshold):
            l += 1

        # Count consecutive dark pixels to the right from the starting point.
        while self.is_dark([point[0], point[1] + r], grey_threshold):
            r += 1

        # Compute estimated dimensions.
        # The center formula includes a small corrective offset to compensate for blur.
        height = u + d
        width = l + r
        center = [point[0] - u + 2 + height // 2, point[1] - l + 2 + width // 2]

        return [center, height, width]

    def find_center(self, point, grey_threshold=None):
        """
        Return only the estimated center of the dark region around a point.

        Parameters:
            point (list[int] | tuple[int, int]): Starting dark pixel.
            grey_threshold (float, optional): Override grey threshold.

        Returns:
            list[int]: Estimated center coordinates.
        """
        return self.center_height_width(point, grey_threshold)[0]
