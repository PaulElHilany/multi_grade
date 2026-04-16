"""
Kivy-based mobile UI for grading multiple-choice answer sheets on Android.

This module implements the mobile grading workflow for MultiGrade, including:
- entering/pasting solution keys,
- choosing per-question weights,
- selecting a test number,
- loading a test image from the device or capturing one with the camera,
- reviewing detection output,
- viewing per-test logs and session summaries,
- storing a persistent grading history.

The UI is defined inline using a Kivy KV string.
"""

import json
import os
import threading
from datetime import datetime
from urllib.parse import urlparse, unquote

from kivy.app import App
from kivy.clock import Clock
from kivy.lang import Builder
from kivy.properties import StringProperty, ListProperty, BooleanProperty
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.screenmanager import Screen
from kivy.utils import platform

from android_camera import AndroidCameraCapture


KV = """
#:import dp kivy.metrics.dp

<RoundButton@Button>:
    background_normal: ""
    background_down: ""
    background_color: 0, 0, 0, 0
    color: 1, 1, 1, 1
    font_size: "22sp"
    canvas.before:
        Color:
            rgba: (0.24, 0.63, 0.80, 1) if self.state == "normal" else (0.18, 0.50, 0.65, 1)
        RoundedRectangle:
            pos: self.pos
            size: self.size
            radius: [18, 18, 18, 18]

<SecondaryRoundButton@Button>:
    background_normal: ""
    background_down: ""
    background_color: 0, 0, 0, 0
    color: 1, 1, 1, 1
    font_size: "18sp"
    canvas.before:
        Color:
            rgba: (0.35, 0.35, 0.35, 1) if self.state == "normal" else (0.25, 0.25, 0.25, 1)
        RoundedRectangle:
            pos: self.pos
            size: self.size
            radius: [18, 18, 18, 18]

<BackArrowButton@Button>:
    text: "<"
    font_size: "26sp"
    bold: True
    size_hint: None, None
    size: "48dp", "48dp"
    background_normal: ""
    background_down: ""
    background_color: 0, 0, 0, 0
    color: 1, 1, 1, 1
    canvas.before:
        Color:
            rgba: 0.25, 0.25, 0.25, 1
        RoundedRectangle:
            pos: self.pos
            size: self.size
            radius: [24, 24, 24, 24]

<CaptureDiscButton@Button>:
    text: ""
    size_hint: None, None
    size: "76dp", "76dp"
    background_normal: ""
    background_down: ""
    background_color: 0, 0, 0, 0
    canvas.before:
        Color:
            rgba: 1, 1, 1, 1
        Ellipse:
            pos: self.pos
            size: self.size
        Color:
            rgba: 0.85, 0.85, 0.85, 1
        Line:
            circle: self.center_x, self.center_y, self.width / 2.2
            width: 1.3

<WeightRow>:
    size_hint_y: None
    height: "44dp"
    spacing: "8dp"

    Label:
        text: root.question_label
        size_hint_x: 0.22
        halign: "left"
        valign: "middle"
        text_size: self.size
        color: 1, 1, 1, 1
        font_size: "17sp"

    Button:
        text: "-"
        size_hint_x: 0.16
        font_size: "18sp"
        on_release: root.decrease_weight()

    TextInput:
        id: weight_input
        text: root.weight_text
        multiline: False
        input_filter: "float"
        size_hint_x: 0.46
        font_size: "17sp"
        on_text: root.weight_text = self.text

    Button:
        text: "+"
        size_hint_x: 0.16
        font_size: "18sp"
        on_release: root.increase_weight()

ScreenManager:
    SolutionKeysScreen:
    WeightsScreen:
    TestNumberScreen:
    LoadTestScreen:
    DuplicateTestNumberScreen:
    DetectionReviewScreen:
    ImagePreviewScreen:
    SingleResultScreen:
    SummaryScreen:
    HistoryScreen:

<SolutionKeysScreen>:
    canvas.before:
        Color:
            rgba: 0.12, 0.07, 0.20, 1
        Rectangle:
            pos: self.pos
            size: self.size
    name: "solution_keys"

    ScrollView:
        do_scroll_x: False

        BoxLayout:
            orientation: "vertical"
            padding: "16dp"
            spacing: "12dp"
            size_hint_y: None
            height: self.minimum_height

            Label:
                text: "Step 1/3: Solution keys"
                font_size: "28sp"
                color: 1, 1, 1, 1
                size_hint_y: None
                height: "56dp"

            Label:
                text: "Paste solution keys (can be read and manually copied from a QR)"
                font_size: "17sp"
                color: 1, 1, 1, 1
                size_hint_y: None
                height: "56dp"
                text_size: self.width, None
                halign: "center"
                valign: "middle"

            Label:
                text: root.status_text
                font_size: "17sp"
                color: 1, 1, 1, 1
                size_hint_y: None
                height: "72dp"
                text_size: self.width, None
                halign: "center"
                valign: "middle"

            TextInput:
                id: pasted_keys_input
                text: root.pasted_keys_text
                multiline: True
                font_size: "17sp"
                size_hint_y: None
                height: "220dp"

            RoundButton:
                text: "Next step"
                size_hint_y: None
                height: "56dp"
                on_release: root.finish_step(pasted_keys_input.text)

            RoundButton:
                text: "View grading log"
                size_hint_y: None
                height: "56dp"
                on_release: root.open_history()

<WeightsScreen>:
    canvas.before:
        Color:
            rgba: 0.12, 0.07, 0.20, 1
        Rectangle:
            pos: self.pos
            size: self.size
    name: "weights"

    BoxLayout:
        orientation: "vertical"
        padding: "16dp"
        spacing: "12dp"

        BoxLayout:
            size_hint_y: None
            height: "48dp"
            spacing: "8dp"

            BackArrowButton:
                on_release: app.root.current = "solution_keys"

            Label:
                text: "Step 2/3: Question weights"
                font_size: "24sp"
                color: 1, 1, 1, 1
                halign: "left"
                valign: "middle"
                text_size: self.size

        Label:
            text: root.info_text
            font_size: "17sp"
            color: 1, 1, 1, 1
            size_hint_y: None
            height: "48dp"
            text_size: self.width, None
            halign: "center"
            valign: "middle"

        Label:
            text: root.status_text
            font_size: "17sp"
            color: 1, 1, 1, 1
            size_hint_y: None
            height: "48dp"
            text_size: self.width, None
            halign: "center"
            valign: "middle"

        ScrollView:
            do_scroll_x: False

            BoxLayout:
                id: weights_container
                orientation: "vertical"
                spacing: "8dp"
                size_hint_y: None
                height: self.minimum_height
                padding: "0dp", "8dp"

        RoundButton:
            text: "Start grading session"
            size_hint_y: None
            height: "56dp"
            on_release: root.start_grading_session()

<TestNumberScreen>:
    canvas.before:
        Color:
            rgba: 0.12, 0.07, 0.20, 1
        Rectangle:
            pos: self.pos
            size: self.size
    name: "test_number"

    BoxLayout:
        orientation: "vertical"
        padding: "16dp"
        spacing: "16dp"

        BoxLayout:
            size_hint_y: None
            height: "48dp"
            spacing: "8dp"

            BackArrowButton:
                on_release: root.go_back()

            Label:
                text: "Step 3/3: Choose test number"
                font_size: "24sp"
                color: 1, 1, 1, 1
                halign: "left"
                valign: "middle"
                text_size: self.size

        Label:
            text: root.status_text
            font_size: "17sp"
            color: 1, 1, 1, 1
            size_hint_y: None
            height: "56dp"
            text_size: self.width, None
            halign: "center"
            valign: "middle"

        Label:
            text: "Test number"
            font_size: "17sp"
            color: 1, 1, 1, 1
            size_hint_y: None
            height: "24dp"
            text_size: self.width, None
            halign: "left"

        BoxLayout:
            size_hint_y: None
            height: "40dp"
            spacing: "8dp"
            size_hint_x: None
            width: "240dp"

            Button:
                text: "-"
                font_size: "17sp"
                size_hint_x: None
                width: "50dp"
                on_release: root.decrease_test_number()

            TextInput:
                id: test_number_input
                text: root.test_number_text
                font_size: "17sp"
                multiline: False
                input_filter: "int"
                on_text: root.test_number_text = self.text

            Button:
                text: "+"
                font_size: "17sp"
                size_hint_x: None
                width: "50dp"
                on_release: root.increase_test_number()

        Widget:

        RoundButton:
            text: "Next step"
            size_hint_y: None
            height: "56dp"
            on_release: root.go_to_load_test()

<LoadTestScreen>:
    canvas.before:
        Color:
            rgba: 0.12, 0.07, 0.20, 1
        Rectangle:
            pos: self.pos
            size: self.size
    name: "load_test"

    BoxLayout:
        orientation: "vertical"
        padding: "16dp"
        spacing: "10dp"

        BoxLayout:
            size_hint_y: None
            height: "48dp"
            spacing: "0dp"

            BackArrowButton:
                on_release: app.root.current = "test_number"

            Label:
                text: "Step 3/3: Grade test"
                font_size: "24sp"
                color: 1, 1, 1, 1
                halign: "left"
                valign: "middle"
                text_size: self.size

        Label:
            text: root.instructions_text
            font_size: "17sp"
            color: 1, 1, 1, 1
            size_hint_y: None
            height: "92dp"
            text_size: self.width, None
            halign: "left"
            valign: "middle"

        BoxLayout:
            orientation: "vertical"
            size_hint_y: 0.48
            spacing: "8dp"

            AnchorLayout:
                anchor_x: "center"
                anchor_y: "center"

                Image:
                    id: guide_or_preview_image
                    source: root.preview_image_source if root.preview_image_source else "guiding_example.jpg"
                    allow_stretch: True
                    keep_ratio: True
                    size_hint: 0.82, 1

        Label:
            text: root.status_text
            font_size: "17sp"
            color: root.status_color
            size_hint_y: None
            height: "56dp"
            text_size: self.width, None
            halign: "center"
            valign: "middle"

        Widget:
            size_hint_y: None
            height: "8dp"

        SecondaryRoundButton:
            text: "Load from device"
            size_hint_y: None
            height: "44dp"
            on_release: root.choose_test_image()
            disabled: root.is_busy

        Widget:
            size_hint_y: None
            height: "10dp"

        AnchorLayout:
            anchor_x: "center"
            anchor_y: "center"
            size_hint_y: None
            height: "64dp"

            CaptureDiscButton:
                on_release: root.capture_test()
                disabled: root.is_busy

        Widget:
            size_hint_y: None
            height: "8dp"

        SecondaryRoundButton:
            text: "Interrupt"
            size_hint_y: None
            height: "44dp"
            on_release: root.interrupt_grading()
            disabled: not root.is_busy

<DuplicateTestNumberScreen>:
    canvas.before:
        Color:
            rgba: 0.12, 0.07, 0.20, 1
        Rectangle:
            pos: self.pos
            size: self.size
    name: "duplicate"

    BoxLayout:
        orientation: "vertical"
        padding: "16dp"
        spacing: "12dp"

        BoxLayout:
            size_hint_y: None
            height: "48dp"
            spacing: "8dp"

            BackArrowButton:
                on_release: app.root.current = "test_number"

            Label:
                text: "Warning"
                font_size: "24sp"
                color: 1, 1, 1, 1
                halign: "left"
                valign: "middle"
                text_size: self.size

        Label:
            text: root.warning_text
            font_size: "17sp"
            color: 1, 1, 1, 1
            text_size: self.width, None
            halign: "center"
            valign: "middle"

        RoundButton:
            text: "Update test number"
            size_hint_y: None
            height: "56dp"
            on_release: root.go_back_to_update()

        RoundButton:
            text: "Overwrite grade"
            size_hint_y: None
            height: "56dp"
            on_release: root.overwrite_grade()

<DetectionReviewScreen>:
    canvas.before:
        Color:
            rgba: 0.12, 0.07, 0.20, 1
        Rectangle:
            pos: self.pos
            size: self.size
    name: "detection_review"

    BoxLayout:
        orientation: "vertical"
        padding: "16dp"
        spacing: "12dp"

        Label:
            text: "Detection review"
            font_size: "24sp"
            color: 1, 1, 1, 1
            size_hint_y: None
            height: "40dp"

        Image:
            id: detection_image
            source: root.image_source
            allow_stretch: True
            keep_ratio: True

        Label:
            text: "Red dots mark unfilled answer boxes."
            font_size: "17sp"
            color: 1, 1, 1, 1
            size_hint_y: None
            height: "40dp"

        RoundButton:
            text: "View test log"
            size_hint_y: None
            height: "56dp"
            on_release: root.view_test_log()

        RoundButton:
            text: "Preview image"
            size_hint_y: None
            height: "56dp"
            on_release: root.preview_image()

        RoundButton:
            text: "Next test"
            size_hint_y: None
            height: "56dp"
            on_release: root.next_test()

        Widget:
            size_hint_y: None
            height: "14dp"

        RoundButton:
            text: "Conclude grading session"
            size_hint_y: None
            height: "56dp"
            on_release: root.conclude_grading_session()

<ImagePreviewScreen>:
    canvas.before:
        Color:
            rgba: 0.12, 0.07, 0.20, 1
        Rectangle:
            pos: self.pos
            size: self.size
    name: "image_preview"

    BoxLayout:
        orientation: "vertical"
        padding: "8dp"
        spacing: "8dp"

        BoxLayout:
            size_hint_y: None
            height: "48dp"
            spacing: "8dp"

            BackArrowButton:
                on_release: root.go_back()

            Label:
                text: "Preview image"
                font_size: "24sp"
                color: 1, 1, 1, 1
                halign: "left"
                valign: "middle"
                text_size: self.size

        Image:
            source: root.image_source
            allow_stretch: True
            keep_ratio: True

<SingleResultScreen>:
    canvas.before:
        Color:
            rgba: 0.12, 0.07, 0.20, 1
        Rectangle:
            pos: self.pos
            size: self.size
    name: "result"

    BoxLayout:
        orientation: "vertical"
        padding: "16dp"
        spacing: "12dp"

        BoxLayout:
            size_hint_y: None
            height: "48dp"
            spacing: "8dp"

            BackArrowButton:
                on_release: app.root.current = "detection_review"

            Label:
                text: "Test Log"
                font_size: "24sp"
                color: 1, 1, 1, 1
                halign: "left"
                valign: "middle"
                text_size: self.size

        TextInput:
            text: root.result_text
            font_size: "17sp"
            readonly: False
            multiline: True

        RoundButton:
            text: "Next test"
            size_hint_y: None
            height: "56dp"
            on_release: root.next_test()

        RoundButton:
            text: "Conclude grading session"
            size_hint_y: None
            height: "56dp"
            on_release: root.finish_session()

<SummaryScreen>:
    canvas.before:
        Color:
            rgba: 0.12, 0.07, 0.20, 1
        Rectangle:
            pos: self.pos
            size: self.size
    name: "summary"

    BoxLayout:
        orientation: "vertical"
        padding: "16dp"
        spacing: "12dp"

        BoxLayout:
            size_hint_y: None
            height: "48dp"
            spacing: "8dp"

            BackArrowButton:
                on_release: app.root.current = "result"

            Label:
                text: "Session Summary"
                font_size: "24sp"
                color: 1, 1, 1, 1
                halign: "left"
                valign: "middle"
                text_size: self.size

        TextInput:
            text: root.summary_text
            font_size: "17sp"
            readonly: False
            multiline: True

        RoundButton:
            text: "View grading log"
            size_hint_y: None
            height: "56dp"
            on_release: root.open_history()

        RoundButton:
            text: "Start new session"
            size_hint_y: None
            height: "56dp"
            on_release: root.start_new_session()

<HistoryScreen>:
    canvas.before:
        Color:
            rgba: 0.12, 0.07, 0.20, 1
        Rectangle:
            pos: self.pos
            size: self.size
    name: "history"

    BoxLayout:
        orientation: "vertical"
        padding: "16dp"
        spacing: "12dp"

        BoxLayout:
            size_hint_y: None
            height: "48dp"
            spacing: "8dp"

            BackArrowButton:
                on_release: root.go_back()

            Label:
                text: "Grading Log"
                font_size: "24sp"
                color: 1, 1, 1, 1
                halign: "left"
                valign: "middle"
                text_size: self.size

        Label:
            text: root.status_text
            font_size: "16sp"
            color: 1, 1, 1, 1
            size_hint_y: None
            height: "32dp"
            text_size: self.width, None
            halign: "center"
            valign: "middle"

        TextInput:
            id: history_text_input
            text: root.history_text
            font_size: "16sp"
            readonly: False
            multiline: True

        RoundButton:
            text: "Refresh log"
            size_hint_y: None
            height: "56dp"
            on_release: root.refresh_history()
"""


class WeightRow(BoxLayout):
    """
    UI row used for editing the weight of one question.

    Each row displays:
    - the question label,
    - a decrement button,
    - a text input,
    - an increment button.
    """
    question_label = StringProperty("")
    weight_text = StringProperty("1")

    def decrease_weight(self):
        """
        Decrease the displayed weight by 1, down to a minimum of 1.
        """
        try:
            v = float(self.weight_text)
        except Exception:
            v = 1.0
        v = max(1.0, v - 1.0)
        self.weight_text = self._fmt(v)

    def increase_weight(self):
        """
        Increase the displayed weight by 1, up to a maximum of 100.
        """
        try:
            v = float(self.weight_text)
        except Exception:
            v = 1.0
        v = min(100.0, v + 1.0)
        self.weight_text = self._fmt(v)

    def get_weight_value(self):
        """
        Parse and validate the current weight value.

        Returns:
            float: Validated numeric weight.

        Raises:
            ValueError: If the value is invalid or outside the allowed range.
        """
        try:
            v = float(self.weight_text)
        except Exception:
            raise ValueError(f"Invalid weight value for {self.question_label}")
        if not (1 <= v <= 100):
            raise ValueError(f"Weight for {self.question_label} must be between 1 and 100.")
        return v

    def _fmt(self, v):
        """
        Format a numeric weight for display.

        Integer values are displayed without a decimal part.

        Parameters:
            v (int | float): Weight value.

        Returns:
            str: Formatted weight string.
        """
        if float(v).is_integer():
            return str(int(v))
        return str(v)


class AppSession:
    """
    In-memory state for the current mobile grading session.
    """

    def __init__(self):
        """
        Initialize an empty grading session.
        """
        self.keys_temp_path = None
        self.weights = None
        self.results = []
        self.key_source_mode = "text"
        self.session_started_at = None
        self.session_solution_keys_text = ""

    def reset_results(self):
        """
        Clear only the graded-result list while preserving the session setup.
        """
        self.results = []

    def clear_all(self):
        """
        Reset the full session state.
        """
        self.keys_temp_path = None
        self.weights = None
        self.results = []
        self.key_source_mode = "text"
        self.session_started_at = None
        self.session_solution_keys_text = ""

    def find_result_index_by_test_number(self, test_number):
        """
        Find the index of a graded result by test number.

        Parameters:
            test_number (int): Test number to search for.

        Returns:
            int | None: Result index if found, otherwise None.
        """
        for i, result in enumerate(self.results):
            if result["test_number"] == test_number:
                return i
        return None


class SolutionKeysScreen(Screen):
    """
    First screen of the mobile workflow where solution keys are pasted.
    """
    status_text = StringProperty("Ready.")
    pasted_keys_text = StringProperty("")

    def finish_step(self, pasted_text):
        """
        Validate and save pasted solution keys, then move to the weights screen.

        Parameters:
            pasted_text (str): Raw solution-key text pasted by the user.
        """
        app = App.get_running_app()
        pasted_text = pasted_text.strip()

        if not pasted_text:
            self.status_text = "Please paste solution keys first."
            return

        try:
            from grading_adapter import save_keys_text_to_temp_file, cleanup_temp_file

            # Remove the previously created temp key file before replacing it.
            if app.session.keys_temp_path:
                cleanup_temp_file(app.session.keys_temp_path)

            app.session.keys_temp_path = save_keys_text_to_temp_file(pasted_text)
            app.session.session_solution_keys_text = pasted_text
            app.session.key_source_mode = "text"
            self.status_text = "Solution keys loaded successfully."

            app.root.get_screen("weights").prepare_weights_screen()
            app.root.current = "weights"

        except ModuleNotFoundError as e:
            self.status_text = f"Failed to load solution keys: {e}"
        except Exception as e:
            self.status_text = f"Failed to load solution keys: {e}"

    def open_history(self):
        """
        Open the persistent grading-history screen.
        """
        app = App.get_running_app()
        screen = app.root.get_screen("history")
        screen.previous_screen = "solution_keys"
        screen.refresh_history()
        app.root.current = "history"


class WeightsScreen(Screen):
    """
    Screen used to assign per-question weights before grading starts.
    """
    status_text = StringProperty("Ready.")
    info_text = StringProperty("")

    def prepare_weights_screen(self):
        """
        Build the per-question weight editor based on the loaded key file.
        """
        app = App.get_running_app()

        try:
            from grading_adapter import expected_question_count
            question_count = expected_question_count(app.session.keys_temp_path)
        except ModuleNotFoundError as e:
            self.status_text = f"Could not determine question count: {e}"
            return
        except Exception as e:
            self.status_text = f"Could not determine question count: {e}"
            return

        self.info_text = f"Detected {question_count} questions."
        self.status_text = "Choose a weight for each question."

        container = self.ids.weights_container
        container.clear_widgets()

        for i in range(question_count):
            row = WeightRow()
            row.question_label = f"Q. {i + 1}"
            row.weight_text = "1"
            container.add_widget(row)

    def collect_weights(self):
        """
        Collect validated weights from all visible weight rows.

        Returns:
            list[float]: Per-question weights in question order.
        """
        container = self.ids.weights_container
        weights = []

        # Kivy children are stored in reverse visual order.
        for row in container.children[::-1]:
            weights.append(row.get_weight_value())

        return weights

    def start_grading_session(self):
        """
        Validate weights, initialize the session, and move to test-number selection.
        """
        app = App.get_running_app()

        try:
            from grading_adapter import validate_weights_against_keys

            weights = self.collect_weights()
            validate_weights_against_keys(app.session.keys_temp_path, weights)

            app.session.weights = weights
            app.session.reset_results()
            app.session.session_started_at = datetime.now().isoformat(timespec="seconds")

            test_number_screen = app.root.get_screen("test_number")
            test_number_screen.reset_for_new_session()
            test_number_screen.previous_screen = "weights"

            self.status_text = "Session started."
            app.root.current = "test_number"

        except ModuleNotFoundError as e:
            self.status_text = str(e)
        except Exception as e:
            self.status_text = str(e)


class TestNumberScreen(Screen):
    """
    Screen used to choose the test number before grading a sheet.
    """
    status_text = StringProperty("Choose a test number.")
    test_number_text = StringProperty("1")
    previous_screen = StringProperty("weights")

    def on_pre_enter(self, *args):
        """
        Automatically suggest the next test number when the screen is shown.
        """
        self._sync_next_test_number()

    def reset_for_new_session(self):
        """
        Reset the test-number screen to its default state.
        """
        self.status_text = "Choose a test number."
        self.test_number_text = "1"
        self.previous_screen = "weights"

    def _sync_next_test_number(self):
        """
        Set the test number to 1 or to the next number after the highest graded test.
        """
        app = App.get_running_app()
        if not app.session.results:
            self.test_number_text = "1"
        else:
            max_test = max(r["test_number"] for r in app.session.results)
            self.test_number_text = str(max_test + 1)

    def increase_test_number(self):
        """
        Increase the test number by 1.
        """
        try:
            v = int(self.test_number_text)
        except Exception:
            v = 1
        self.test_number_text = str(v + 1)

    def decrease_test_number(self):
        """
        Decrease the test number by 1, down to a minimum of 1.
        """
        try:
            v = int(self.test_number_text)
        except Exception:
            v = 1
        self.test_number_text = str(max(1, v - 1))

    def go_back(self):
        """
        Return to the previous screen.
        """
        App.get_running_app().root.current = self.previous_screen

    def go_to_load_test(self):
        """
        Validate the selected test number and move to the test-loading screen.
        """
        app = App.get_running_app()

        if not app.session.keys_temp_path or app.session.weights is None:
            self.status_text = "Session is not initialized."
            return

        if not self.test_number_text.strip():
            self.status_text = "Test number is required."
            return

        try:
            test_number = int(self.test_number_text.strip())
        except ValueError:
            self.status_text = "Test number must be an integer."
            return

        app.pending_test_number = test_number

        load_screen = app.root.get_screen("load_test")
        load_screen.reset_preview_to_guide()
        load_screen.set_normal_status(f"Ready to grade test number {test_number}.")
        app.root.current = "load_test"


class LoadTestScreen(Screen):
    """
    Screen used to load or capture a test image and launch grading.
    """
    status_text = StringProperty("Ready.")
    status_color = ListProperty([1, 1, 1, 1])
    preview_image_source = StringProperty("")
    is_busy = BooleanProperty(False)
    instructions_text = StringProperty(
        "Photo of test sheet should not exceed test paper boundary. It should include\n"
        "1 - the test number\n"
        "2 - the four corner-markings, and\n"
        "3 - at least half of the black rectangle to the right"
    )

    def set_normal_status(self, text):
        """
        Display a normal white status message.

        Parameters:
            text (str): Status message.
        """
        self.status_text = text
        self.status_color = [1, 1, 1, 1]

    def set_busy_status(self, text):
        """
        Display a busy/in-progress status message in red.

        Parameters:
            text (str): Status message.
        """
        self.status_text = text
        self.status_color = [1, 0, 0, 1]

    def reset_preview_to_guide(self):
        """
        Clear the preview image so the guide image is shown again.
        """
        self.preview_image_source = ""

    def capture_test(self):
        """
        Start the camera-based grading flow for the currently selected test number.
        """
        app = App.get_running_app()

        try:
            self._ensure_pending_test_number()

            # Prevent accidental duplicate test numbers unless the user explicitly overwrites.
            if app.session.find_result_index_by_test_number(app.pending_test_number) is not None:
                duplicate_screen = app.root.get_screen("duplicate")
                duplicate_screen.warning_text = (
                    f"Test number {app.pending_test_number} already exists.\n"
                    f"Load updated photo for test number '{app.pending_test_number}'."
                )
                app.pending_action = "camera"
                app.root.current = "duplicate"
                return

        except Exception as e:
            self.set_normal_status(str(e))
            return

        app.request_needed_permissions(self._after_test_permissions)

    def choose_test_image(self):
        """
        Start the device-file grading flow for the currently selected test number.
        """
        app = App.get_running_app()

        try:
            self._ensure_pending_test_number()

            if app.session.find_result_index_by_test_number(app.pending_test_number) is not None:
                duplicate_screen = app.root.get_screen("duplicate")
                duplicate_screen.warning_text = (
                    f"Test number {app.pending_test_number} already exists.\n"
                    f"Load updated photo for test number '{app.pending_test_number}'."
                )
                app.pending_action = "device"
                app.root.current = "duplicate"
                return

        except Exception as e:
            self.set_normal_status(str(e))
            return

        self._open_device_file()

    def interrupt_grading(self):
        """
        Mark the current grading operation as interrupted and return to test selection.
        """
        app = App.get_running_app()
        app.interrupt_requested = True
        self.is_busy = False
        self.reset_preview_to_guide()
        self.set_normal_status("Grading interrupted.")
        app.root.current = "test_number"

    def _ensure_pending_test_number(self):
        """
        Ensure that a test number was selected before capture/loading begins.

        Raises:
            ValueError: If no pending test number is set.
        """
        app = App.get_running_app()
        if app.pending_test_number is None:
            raise ValueError("Please choose a test number first.")

    def _open_device_file(self):
        """
        Open the platform file chooser for selecting a test image from the device.
        """
        self.set_normal_status("Choose a previously taken test image...")

        try:
            from plyer import filechooser
            filechooser.open_file(
                on_selection=self._test_file_selected,
                filters=["*.png", "*.jpg", "*.jpeg"]
            )
        except Exception as e:
            self.set_normal_status(f"File chooser error: {e}")

    def _test_file_selected(self, selection):
        """
        Kivy callback wrapper for deferred processing of file-chooser output.

        Parameters:
            selection: Raw selection object returned by the file chooser.
        """
        Clock.schedule_once(lambda dt: self._handle_test_file_selection(selection), 0)

    def _handle_test_file_selection(self, selection):
        """
        Validate a selected device file and launch image processing.

        Parameters:
            selection: Raw selection object returned by the file chooser.
        """
        chosen_path = normalize_selection_to_path(selection)

        if not chosen_path:
            self.set_normal_status("No valid test image file was returned.")
            return

        if not os.path.exists(chosen_path):
            self.set_normal_status("Selected test image does not exist or is inaccessible.")
            return

        self._process_test_image(chosen_path)

    def _after_test_permissions(self, granted):
        """
        Continue camera capture after the permission request completes.

        Parameters:
            granted (bool): Whether the required permissions were granted.
        """
        if not granted:
            self.set_normal_status("Permission denied.")
            return

        self.set_normal_status("Opening camera for test capture...")

        try:
            app = App.get_running_app()
            image_file = app.get_app_file_path("captured_test.jpg")
            app.android_camera.capture(image_file, self._test_captured)
        except Exception as e:
            self.set_normal_status(f"Test camera error: {e}")

    def _test_captured(self, path):
        """
        Kivy callback wrapper for deferred processing of a captured image.

        Parameters:
            path (str): Path to the captured image.
        """
        Clock.schedule_once(lambda dt: self._handle_test_result(path), 0)

    def _handle_test_result(self, path):
        """
        Validate the captured camera result and launch grading.

        Parameters:
            path (str): Path to the captured image.
        """
        if not path or not os.path.exists(path):
            self.set_normal_status("Test capture failed.")
            return

        self._process_test_image(path)

    def _process_test_image(self, path):
        """
        Start background grading for the selected test image.

        Parameters:
            path (str): Path to the test image file.
        """
        app = App.get_running_app()
        app.interrupt_requested = False
        self.preview_image_source = path
        self.is_busy = True
        self.set_busy_status(
            f"Grading test number {app.pending_test_number}, this will take a few seconds..."
        )

        # Run heavy grading in a background thread so the UI stays responsive.
        worker = threading.Thread(
            target=self._do_process_test_image_worker,
            args=(path,),
            daemon=True,
        )
        worker.start()

    def _do_process_test_image_worker(self, path):
        """
        Background worker that runs grading and prepares review output.

        Parameters:
            path (str): Path to the test image file.
        """
        app = App.get_running_app()

        try:
            from grading_adapter import grade_single_test_structured

            sensitivity = 4

            result = grade_single_test_structured(
                image_path=path,
                keys_path=app.session.keys_temp_path,
                weights=app.session.weights,
                test_number=app.pending_test_number,
                color_thr_sensitivity=sensitivity,
            )

            if app.interrupt_requested:
                Clock.schedule_once(lambda dt: self._handle_interrupted_grading(), 0)
                return

            review_image_path = app.create_detection_review_image(
                source_image_path=path,
                detections=result.get("detections", []),
                test_number=result["test_number"],
            )
            result["review_image_path"] = review_image_path

            Clock.schedule_once(
                lambda dt: self._handle_grading_success(result, review_image_path),
                0,
            )

        except ModuleNotFoundError as e:
            Clock.schedule_once(
                lambda dt: self._handle_grading_failure(f"Grading failed: {e}"),
                0,
            )
        except Exception as e:
            Clock.schedule_once(
                lambda dt: self._handle_grading_failure(f"Grading failed: {e}"),
                0,
            )

    def _handle_interrupted_grading(self):
        """
        Restore the screen state after a user interruption.
        """
        self.is_busy = False
        self.reset_preview_to_guide()
        self.set_normal_status("Grading interrupted.")

    def _handle_grading_success(self, result, review_image_path):
        """
        Save successful grading output and move to the detection-review screen.

        Parameters:
            result (dict): Structured grading result.
            review_image_path (str): Path to the generated review image.
        """
        app = App.get_running_app()

        index = app.session.find_result_index_by_test_number(result["test_number"])
        if index is None:
            app.session.results.append(result)
        else:
            app.session.results[index] = result

        app.last_result = result
        self.is_busy = False
        self.set_normal_status("Test graded successfully.")

        review_screen = app.root.get_screen("detection_review")
        review_screen.image_source = review_image_path
        app.root.current = "detection_review"

    def _handle_grading_failure(self, message):
        """
        Display a grading-failure message.

        Parameters:
            message (str): Failure message to display.
        """
        self.is_busy = False
        self.set_normal_status(message)

    def continue_pending_action(self):
        """
        Resume the previously blocked action after duplicate-number confirmation.
        """
        app = App.get_running_app()
        if app.pending_action == "device":
            self._open_device_file()
        elif app.pending_action == "camera":
            app.request_needed_permissions(self._after_test_permissions)


class DuplicateTestNumberScreen(Screen):
    """
    Warning screen shown when the selected test number already exists in the session.
    """
    warning_text = StringProperty("")

    def go_back_to_update(self):
        """
        Return to the test-number screen so the user can choose another number.
        """
        App.get_running_app().root.current = "test_number"

    def overwrite_grade(self):
        """
        Remove the existing grade for the current test number and continue.
        """
        app = App.get_running_app()
        test_number = app.pending_test_number
        index = app.session.find_result_index_by_test_number(test_number)

        if index is not None:
            del app.session.results[index]

        app.root.current = "load_test"
        app.root.get_screen("load_test").continue_pending_action()


class DetectionReviewScreen(Screen):
    """
    Screen showing the image with detected answer-box markers.
    """
    image_source = StringProperty("")

    def view_test_log(self):
        """
        Open the text log for the most recently graded test.
        """
        app = App.get_running_app()
        result_screen = app.root.get_screen("result")
        result_screen.result_text = app.format_single_result_text(app.last_result)
        app.root.current = "result"

    def preview_image(self):
        """
        Open a larger preview of the current review image.
        """
        app = App.get_running_app()
        preview_screen = app.root.get_screen("image_preview")
        preview_screen.image_source = self.image_source
        preview_screen.previous_screen = "detection_review"
        app.root.current = "image_preview"

    def next_test(self):
        """
        Return to test-number selection for grading the next test.
        """
        app = App.get_running_app()
        app.root.get_screen("load_test").reset_preview_to_guide()
        test_number_screen = app.root.get_screen("test_number")
        test_number_screen._sync_next_test_number()
        test_number_screen.previous_screen = "detection_review"
        app.root.current = "test_number"

    def conclude_grading_session(self):
        """
        Build the session summary, save the session to history, and show the summary screen.
        """
        app = App.get_running_app()
        summary_screen = app.root.get_screen("summary")
        summary_screen.summary_text = app.build_summary_text()
        app.append_current_session_to_history()
        app.root.current = "summary"


class ImagePreviewScreen(Screen):
    """
    Full-screen preview of the current review image.
    """
    image_source = StringProperty("")
    previous_screen = StringProperty("detection_review")

    def go_back(self):
        """
        Return to the previous screen.
        """
        App.get_running_app().root.current = self.previous_screen


class SingleResultScreen(Screen):
    """
    Screen showing the text log for one graded test.
    """
    result_text = StringProperty("")

    def next_test(self):
        """
        Return to test-number selection for grading the next test.
        """
        app = App.get_running_app()
        app.root.get_screen("load_test").reset_preview_to_guide()
        test_number_screen = app.root.get_screen("test_number")
        test_number_screen._sync_next_test_number()
        test_number_screen.previous_screen = "detection_review"
        app.root.current = "test_number"

    def finish_session(self):
        """
        Build the session summary, save the session to history, and show the summary screen.
        """
        app = App.get_running_app()
        summary_screen = app.root.get_screen("summary")
        summary_screen.summary_text = app.build_summary_text()
        app.append_current_session_to_history()
        app.root.current = "summary"


class SummaryScreen(Screen):
    """
    Screen displaying the full grading-session summary.
    """
    summary_text = StringProperty("")

    def open_history(self):
        """
        Open the persistent grading-history screen.
        """
        app = App.get_running_app()
        screen = app.root.get_screen("history")
        screen.previous_screen = "summary"
        screen.refresh_history()
        app.root.current = "history"

    def start_new_session(self):
        """
        Reset the mobile app state and begin a new grading session.
        """
        app = App.get_running_app()

        try:
            from grading_adapter import cleanup_temp_file

            if app.session.keys_temp_path:
                cleanup_temp_file(app.session.keys_temp_path)
        except Exception:
            pass

        app.session.clear_all()
        app.pending_test_number = None
        app.pending_action = None
        app.last_result = None
        app.interrupt_requested = False

        solution_screen = app.root.get_screen("solution_keys")
        solution_screen.status_text = "Ready."
        solution_screen.pasted_keys_text = ""

        app.root.get_screen("weights").status_text = "Ready."
        app.root.get_screen("weights").info_text = ""
        app.root.get_screen("test_number").reset_for_new_session()

        load_screen = app.root.get_screen("load_test")
        load_screen.set_normal_status("Ready.")
        load_screen.preview_image_source = ""
        load_screen.is_busy = False

        app.root.get_screen("detection_review").image_source = ""
        app.root.get_screen("image_preview").image_source = ""
        app.root.get_screen("image_preview").previous_screen = "detection_review"

        self.summary_text = ""
        app.root.current = "solution_keys"


class HistoryScreen(Screen):
    """
    Screen displaying the persistent grading history stored on the device.
    """
    history_text = StringProperty("")
    status_text = StringProperty("Persistent grading log.")
    previous_screen = StringProperty("solution_keys")

    def on_pre_enter(self, *args):
        """
        Refresh the grading history whenever the screen is entered.
        """
        self.refresh_history()

    def refresh_history(self):
        """
        Load and display the saved grading history.
        """
        app = App.get_running_app()
        try:
            entries = app.load_history_entries()
            self.history_text = app.format_history_entries(entries)
            timestamp = datetime.now().strftime("%H:%M:%S")
            self.status_text = f"Persistent grading log. Refreshed at {timestamp}."
        except Exception as e:
            self.history_text = ""
            self.status_text = f"Failed to load log: {e}"

    def go_back(self):
        """
        Return to the previous screen.
        """
        App.get_running_app().root.current = self.previous_screen


def normalize_selection_to_path(selection):
    """
    Normalize a file-chooser selection into a usable local file path.

    Supported input forms include:
    - plain string paths
    - bytes paths
    - one-item lists/tuples
    - file:// URIs

    Parameters:
        selection: Raw selection object returned by the file chooser.

    Returns:
        str | None: Normalized file path, or None if no valid path is available.
    """
    if not selection:
        return None

    item = selection

    if isinstance(selection, (list, tuple)):
        if len(selection) == 0:
            return None
        item = selection[0]

    if not item:
        return None

    if isinstance(item, bytes):
        try:
            item = item.decode("utf-8")
        except Exception:
            return None

    if not isinstance(item, str):
        return None

    item = item.strip()
    if not item:
        return None

    if item.startswith("file://"):
        parsed = urlparse(item)
        item = unquote(parsed.path)

    return item


class MultiTestGraderApp(App):
    """
    Main Kivy application class for the mobile grading workflow.
    """

    def build(self):
        """
        Initialize application state and build the Kivy UI.

        Returns:
            Widget: Root widget loaded from the KV layout string.
        """
        self.session = AppSession()
        self.pending_test_number = None
        self.pending_action = None
        self.last_result = None
        self.interrupt_requested = False
        self.android_camera = AndroidCameraCapture() if platform == "android" else None
        return Builder.load_string(KV)

    def get_app_file_path(self, filename):
        """
        Build an app-private file path under the user data directory.

        Parameters:
            filename (str): Filename to place in the app data directory.

        Returns:
            str: Full file path.
        """
        os.makedirs(self.user_data_dir, exist_ok=True)
        return os.path.join(self.user_data_dir, filename)

    def get_history_file_path(self):
        """
        Return the path of the persistent grading-history file.

        Returns:
            str: JSON history file path.
        """
        os.makedirs(self.user_data_dir, exist_ok=True)
        return os.path.join(self.user_data_dir, "grading_history.json")

    def get_review_images_dir(self):
        """
        Return the directory used to store generated review images.

        Returns:
            str: Review-image directory path.
        """
        path = os.path.join(self.user_data_dir, "review_images")
        os.makedirs(path, exist_ok=True)
        return path

    def request_needed_permissions(self, callback):
        """
        Request required runtime permissions when running on Android.

        Parameters:
            callback (callable): Function called with a boolean granted flag.
        """
        if self._is_android():
            self._request_android_permissions(callback)
        else:
            callback(True)

    def _is_android(self):
        """
        Check whether the app is currently running on Android.

        Returns:
            bool: True on Android, otherwise False.
        """
        return platform == "android"

    def _request_android_permissions(self, callback):
        """
        Request Android camera and storage permissions.

        Parameters:
            callback (callable): Function called with a boolean granted flag.
        """
        try:
            from android.permissions import request_permissions, Permission

            permissions = [
                Permission.CAMERA,
                Permission.READ_EXTERNAL_STORAGE,
                Permission.WRITE_EXTERNAL_STORAGE,
            ]

            def android_permission_callback(permissions_list, grants):
                """
                Convert Android permission callback output into one granted flag.
                """
                granted = all(grants)
                Clock.schedule_once(lambda dt: callback(granted), 0)

            request_permissions(permissions, android_permission_callback)

        except Exception:
            # Fall back to assuming success on platforms/environments where the
            # Android permission API is unavailable.
            callback(True)

    def format_single_result_text(self, result):
        """
        Build a human-readable text log for one graded test.

        Parameters:
            result (dict): Structured result dictionary.

        Returns:
            str: Formatted result text.
        """
        lines = [result.get("display_text", "")]

        questions = result.get("questions", [])
        if questions:
            lines.append("")
            lines.append("Question log:")

            for q in questions:
                qn = q.get("question_number", "?")
                status = "correct" if q.get("is_correct") else "wrong"
                student_answer = q.get("student_answer", [])
                correct_answer = q.get("correct_answer", [])

                lines.append(
                    f"Q{qn}: {status} | answer={student_answer} | key={correct_answer}"
                )

        return "\n".join(lines)

    def create_detection_review_image(self, source_image_path, detections, test_number):
        """
        Create a review image with red dots over unfilled detected answer boxes.

        Parameters:
            source_image_path (str): Path to the source test image.
            detections (list[dict]): Detection metadata returned by grading.
            test_number (int): Test number used in the output filename.

        Returns:
            str: Path to the saved review image.

        Raises:
            RuntimeError: If Pillow is unavailable.
        """
        try:
            from PIL import Image, ImageDraw, ImageOps
        except Exception as e:
            raise RuntimeError(f"Pillow is required to create review image: {e}")

        image = Image.open(source_image_path)
        image = ImageOps.exif_transpose(image).convert("RGB")
        draw = ImageDraw.Draw(image)

        radius = max(4, int(min(image.size) * 0.006))

        for item in detections:
            if item.get("filled"):
                continue

            center = item.get("center", [0, 0])
            y, x = center[0], center[1]

            left = x - radius
            top = y - radius
            right = x + radius
            bottom = y + radius

            draw.ellipse((left, top, right, bottom), fill=(255, 0, 0), outline=(255, 0, 0))

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        out_path = os.path.join(
            self.get_review_images_dir(),
            f"review_test_{test_number}_{timestamp}.png"
        )
        image.save(out_path)
        return out_path

    def build_summary_text(self):
        """
        Build the full text summary for the current grading session.

        Returns:
            str: Session summary text including average grade when available.
        """
        if not self.session.results:
            return "No tests were graded."

        sorted_results = sorted(self.session.results, key=lambda x: x["test_number"])

        lines = []
        numeric_grades = []

        for result in sorted_results:
            lines.append(self.format_single_result_text(result))
            lines.append("")

            if result.get("grade") is not None:
                numeric_grades.append(result["grade"])

        text = "\n".join(lines).strip()

        if numeric_grades:
            avg = sum(numeric_grades) / len(numeric_grades)
            text += f"\n\nAverage grade: {avg:.2f}"
        else:
            text += "\n\nAverage grade: unavailable"

        return text

    def load_history_entries(self):
        """
        Load persistent grading-history entries from disk.

        Returns:
            list: Saved history entries, or an empty list if no history exists.
        """
        path = self.get_history_file_path()
        if not os.path.exists(path):
            return []

        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)

        if not isinstance(data, list):
            return []

        return data

    def save_history_entries(self, entries):
        """
        Save persistent grading-history entries to disk.

        Parameters:
            entries (list): History entries to save.
        """
        path = self.get_history_file_path()
        with open(path, "w", encoding="utf-8") as f:
            json.dump(entries, f, ensure_ascii=False, indent=2)

    def append_current_session_to_history(self):
        """
        Append the current completed session to the persistent grading history.
        """
        if not self.session.results:
            return

        entries = self.load_history_entries()

        session_entry = {
            "saved_at": datetime.now().isoformat(timespec="seconds"),
            "session_started_at": self.session.session_started_at,
            "solution_keys_text": self.session.session_solution_keys_text,
            "weights": self.session.weights,
            "results": sorted(self.session.results, key=lambda x: x["test_number"]),
        }

        entries.append(session_entry)
        self.save_history_entries(entries)

    def format_history_entries(self, entries):
        """
        Format saved history entries into a readable text block.

        Parameters:
            entries (list): History entries loaded from disk.

        Returns:
            str: Human-readable grading-history text.
        """
        if not entries:
            return "No grading log entries yet."

        blocks = []

        for i, entry in enumerate(entries, start=1):
            saved_at = entry.get("saved_at", "unknown")
            started_at = entry.get("session_started_at", "unknown")
            solution_keys_text = entry.get("solution_keys_text", "")
            weights = entry.get("weights", [])
            results = entry.get("results", [])

            lines = [
                f"Session {i}",
                f"Saved at: {saved_at}",
                f"Started at: {started_at}",
                "",
                "Solution keys:",
                solution_keys_text if solution_keys_text else "(none)",
                "",
                f"Weights: {weights}",
                "",
                "Results:",
            ]

            if results:
                for result in results:
                    lines.append(self.format_single_result_text(result))
                    lines.append("")
            else:
                lines.append("(no results)")

            blocks.append("\n".join(lines))

        return "\n\n" + ("\n\n" + ("-" * 40) + "\n\n").join(blocks)

    def on_stop(self):
        """
        Clean up temporary key files when the app stops.
        """
        try:
            from grading_adapter import cleanup_temp_file

            if hasattr(self, "session") and self.session.keys_temp_path:
                cleanup_temp_file(self.session.keys_temp_path)
        except Exception:
            pass


if __name__ == "__main__":
    MultiTestGraderApp().run()
