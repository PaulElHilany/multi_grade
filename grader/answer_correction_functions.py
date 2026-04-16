"""
Answer-comparison and grading utilities for MultiGrade.

This module provides helper functions to:
- compare a student's selected answers to the correct solution,
- compute per-question correctness,
- compute weighted total grades,
- generate detailed per-question grading summaries.
"""


def answer_list_compare(answer_list, solution_list):
    """
    Compare one student's answer list to the corresponding solution list.

    The returned tuple summarizes:
    - n: total number of choices
    - k: number of correct choices in the solution
    - w: number of mismatches between answer and solution
    - c: number of correctly selected correct choices

    Parameters:
        answer_list (list[int]): Student answer row as 0/1 values.
        solution_list (list[int]): Correct answer row as 0/1 values.

    Returns:
        tuple[int, int, int, int]:
            - total number of choices
            - number of correct choices
            - number of mismatches
            - number of correctly selected correct choices
    """
    # Total number of answer choices for this question.
    n = len(solution_list)

    # Number of correct choices in the official solution.
    k = sum(solution_list)

    # Number of mismatched positions between student answer and solution.
    w = sum(abs(solution_list[i] - answer_list[i]) for i in range(n))

    # Number of correctly selected correct choices.
    c = sum(solution_list[i] * answer_list[i] for i in range(n))

    return n, k, w, c


def answer_list_grade(comparison_list):
    """
    Grade one question from its comparison summary.

    Current grading rule:
    - full credit only if there is no mismatch
    - otherwise zero credit

    Parameters:
        comparison_list (tuple[int, int, int, int]): Output from answer_list_compare().

    Returns:
        int: 1 if fully correct, otherwise 0.
    """
    if comparison_list[2] == 0:
        return 1
    return 0


def total_grade(grades_list: list, weights_list: list):
    """
    Compute a weighted total grade from per-question raw grades.

    Parameters:
        grades_list (list[int | float]): Per-question raw grades.
        weights_list (list[int | float]): Per-question weights.

    Returns:
        int | float: Weighted total grade.
    """
    grade = sum(grades_list[i] * weights_list[i] for i in range(len(weights_list)))
    return grade


def question_result(answer_list, solution_list, weight, question_number):
    """
    Build a detailed grading summary for one question.

    Parameters:
        answer_list (list[int]): Student answer row.
        solution_list (list[int]): Correct answer row.
        weight (int | float): Weight assigned to this question.
        question_number (int): 1-based question number.

    Returns:
        dict: Detailed question result including correctness, raw grade,
        weighted grade, answer data, and comparison statistics.
    """
    comparison = answer_list_compare(answer_list, solution_list)
    raw_grade = answer_list_grade(comparison)
    weighted_grade = raw_grade * weight
    is_correct = raw_grade == 1

    return {
        "question_number": question_number,
        "is_correct": is_correct,
        "raw_grade": raw_grade,
        "weight": weight,
        "question_grade": weighted_grade,
        "student_answer": answer_list,
        "correct_answer": solution_list,
        "comparison": {
            "n": comparison[0],
            "k": comparison[1],
            "w": comparison[2],
            "c": comparison[3],
        },
    }


def total_grade_single(answers, solutions, weights):
    """
    Compute the weighted total grade for a single test.

    Parameters:
        answers (list[list[int]]): Student answers for all questions.
        solutions (list[list[int]]): Correct answers for all questions.
        weights (list[int | float]): Per-question weights.

    Returns:
        int | float: Weighted total grade.
    """
    grades = [
        answer_list_grade(answer_list_compare(answers[i], solutions[i]))
        for i in range(len(solutions))
    ]
    return total_grade(grades, weights)


def detailed_total_grade_single(answers, solutions, weights):
    """
    Compute a detailed weighted grading summary for a single test.

    Parameters:
        answers (list[list[int]]): Student answers for all questions.
        solutions (list[list[int]]): Correct answers for all questions.
        weights (list[int | float]): Per-question weights.

    Returns:
        dict: Dictionary containing:
            - total_grade
            - questions: detailed per-question grading results
    """
    details = []

    for i in range(len(solutions)):
        details.append(
            question_result(
                answer_list=answers[i],
                solution_list=solutions[i],
                weight=weights[i],
                question_number=i + 1,
            )
        )

    total = sum(item["question_grade"] for item in details)

    return {
        "total_grade": total,
        "questions": details,
    }


def total_grade_all(t_answers, t_solutions, weights):
    """
    Compute weighted total grades for multiple tests.

    Parameters:
        t_answers (list[list[list[int]]]): Answers for all tests.
        t_solutions (list[list[list[int]]]): Solutions for all tests.
        weights (list[int | float]): Per-question weights.

    Returns:
        list[int | float]: Total grade for each test.
    """
    grades = [
        total_grade_single(t_answers[i], t_solutions[i], weights)
        for i in range(len(t_solutions))
    ]
    return grades
