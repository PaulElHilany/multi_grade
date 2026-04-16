# MultiGrade

MultiGrade is a tool for creating and grading multiple-choice answer sheets.

It supports two main tasks:

- generating numbered answer sheets and correction keys before an exam
- grading completed answer sheets either:
  - in batch from scanned PDF files
  - individually from photos on an Android phone

The project is designed to reduce grading time, support anti-cheating through answer-order shuffling, and make grading results easier to verify visually.

## Features

- Generate numbered answer sheets as PDF files
- Generate correction keys as text, PDF, and QR code
- Support up to:
  - 30 questions
  - 8 choices per question
- Anti-cheating support through multiple correction schemes
- Batch grading from scanned PDF files
- Mobile grading from phone photos
- Visual grading output for easier verification
- Grade list and average score generation

## Main programs

### `create_answer_sheets/sheet_generator_ui.py`

This program generates the materials needed before an exam.

It creates:

- numbered answer sheets in PDF format
- correction keys in text format
- a human-readable correction reference in PDF format
- a QR code image for mobile import

### `grader/batch_grade_ui.py`

This program is intended for grading a larger number of completed answer sheets.

Typical use:

1. Collect completed answer sheets.
2. Arrange them in increasing order by test number.
3. Scan them into a single PDF file.
4. Load the answer keys.
5. Run the grader.

It outputs:

- grades for all tests
- average grade
- a PDF showing how the grading was interpreted
- a text log of grading details

> Important: test numbers are not automatically read in the batch workflow, so sheets must be ordered correctly before scanning.

### `grader/mobile_grade_ui.py`

This program is intended for grading a smaller number of tests using an Android phone.

The user:

- pastes the solution key text into the app
- selects the test number
- takes a photo of a test sheet or loads one from the phone

For each test, the app shows:

- a visual interpretation of the detected answer boxes
- a grading log

After grading multiple tests, the app returns:

- the list of grades
- the average grade

## Typical workflow

### 1. Prepare the exam

Create the multiple-choice exam.

Current supported limits:

- maximum 30 questions
- maximum 8 choices per question

### 2. Generate answer sheets and correction keys

Use `sheet_generator_ui.py` to enter:

- the answer scheme as `0/1` values
  - `1` = correct choice
  - `0` = incorrect choice
- the number of tests to generate

### 3. Generated output files

The generator creates files such as:

- `tests_{date}_{time}.pdf` — numbered answer sheets
- `sol_keys_{date}_{time}.txt` — correction keys
- `sol_keys_qr_{date}_{time}.png` — QR code for mobile import
- `sol_keys_ref_{date}_{time}.pdf` — human-readable reference

Each test number is associated with one of three correction schemes.

### 4. Adjust the exam answer order

Before printing, rearrange the answer-choice order according to the generated correction reference.

This supports anti-cheating by giving nearby students different answer orders.

### 5. Print and distribute

- print the generated numbered answer sheets
- distribute them with the corresponding exams
- keep extra blank sheets available if needed

### 6. Grade the completed tests

#### Option A: Batch grading

Use `batch_grade_ui.py` to:

- load answer keys
- load a scanned PDF of completed answer sheets
- enter question weights
- generate grades and reports

#### Option B: Mobile grading

Use `mobile_grade_ui.py` to:

- paste the answer keys
- photograph or load a test image
- enter the test number
- review the detection result and grading log
- repeat for each test


## Project structure

```text
.
├── .gitignore
├── LICENSE
├── README.md
├── requirements.txt
├── batch_grade_ui.spec
├── manual/
│   └── user_manual.pdf
├── create_answer_sheets/
│   ├── create_answer_sheets.py
│   ├── create_answer_sheets_functions.py
│   ├── create_solution_keys.py
│   └── sheet_generator_ui.py
└── grader/
    ├── android_camera.py
    ├── answer_correction_functions.py
    ├── batch_grade_ui.py
    ├── batch_reporting.py
    ├── batch_visualization.py
    ├── grading_adapter.py
    ├── image_analyzing_functions.py
    ├── mobile_grade_ui.py
    ├── multi_grade.py
    ├── multi_grade_mobile.py
    └── pattern_extraction_functions.py

```

## Requirements

### Desktop version

- Python 3.10+ recommended
- Windows, macOS, or Linux
- Enough storage for input, temporary, and output files

### Mobile version

- Android device
- Rear camera
- Camera and file permissions enabled
- Enough free storage for temporary images and logs

The mobile app is currently not supported on iOS.

## Installation

### Desktop

Install Python dependencies:

[A text should be entered here]

Also install:

- a TeX distribution with `pdflatex`:
  - TeX Live, or
  - MiKTeX
- Poppler, required by `pdf2image`

### Windows executable version

If packaged `.exe` files are provided, they can be run directly on Windows without installing Python separately.

### Mobile

Install Python dependencies:

[A text should be entered here]

If installing a packaged Android app, install the provided `.apk` and allow the requested permissions.

If building for Android, also configure your Kivy/Buildozer setup as needed.

## Dependencies

### Desktop Python dependencies

- `numpy`
- `opencv-python`
- `pdf2image`
- `qrcode`
- `reportlab`
- `Pillow`

### Mobile Python dependencies

- `numpy`
- `opencv-python`
- `Pillow`
- `kivy`
- `plyer`
- `pyjnius`

### System dependencies

#### LaTeX

PDF and form generation use `pdflatex`, so you need a TeX distribution installed.

Required LaTeX packages include:

- `amsart`
- `tikz-cd`
- `atbegshi`

#### Poppler

`pdf2image` requires Poppler, especially on Windows.

Make sure Poppler is installed and available on your system `PATH`.

#### Android notes

For Android builds, dependencies are often managed through Buildozer or related packaging configuration rather than only through `pip`.

Mobile features also rely on Android platform components such as:

- camera intent support
- file sharing / `FileProvider`
- runtime permissions

## Input and output

### Supported input formats

- `.png`
- `.pdf`
- `.jpg`
- `.jpeg`

### Output generated by the project

#### Sheet generator

- numbered answer sheets
- correction keys
- correction reference
- QR image for mobile import

#### Batch grader

- PDF showing detected answers for all processed tests
- text grading log
- grade list and average grade

#### Mobile grader

- visual result image for each processed test
- grade list and average grade

## Instructions for students

Students should be instructed to:

- avoid filling in the final answer sheet until the last few minutes of the exam
- use a dark ink pen, not pencil
- fill the selected answer box completely
- request a new answer sheet if they make a mistake

## Photo-taking guidelines

For mobile grading:

- do not include the edges of the paper in the photo
- include all corner squares
- include at least half of the large black square on the right-hand edge
- include the exam number

## Limitations

Current limitations include:

- maximum 30 questions
- maximum 8 choices per question
- no automatic test number recognition in the batch workflow
- mobile app support is Android only

## Future improvements

Possible future improvements:

- automatic test number recognition
- support for more questions
- additional grading statistics
- additional correction schemes

## Documentation

The full user guide is available in:

- `user_manual.pdf`

## Downloads

Prebuilt application files are available from the GitHub Releases page:

- Windows answer sheet generator executable
- Windows batch grader executable
- Android mobile grading APK

Latest release:

- [MultiGrade Releases](https://github.com/PaulElHilany/multi_grade/releases)

Typical release assets include:

- `MultiGrade-answer-sheet-generator-v1.0.exe`
- `MultiGrade-batch-grader-windows-v1.0.exe`
- `MultiGrade-mobile-android-v1.0.apk`

### Notes

- Windows may show a SmartScreen warning for unsigned executables.
- Android users may need to allow installation from unknown sources to install the APK manually.
- Source code and documentation remain available in this repository.


## Contact

- Email: boulos.hilani@gmail.com
- Website: <https://boulos-elhilany.com/>