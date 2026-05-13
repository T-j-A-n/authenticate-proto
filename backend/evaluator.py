import subprocess
import tempfile
import os
import time
import json
import math
from runner import run_code


def profile_complexity(code: str, problem: dict) -> str:
    problem_id = problem.get("id", "")
    sizes = [100, 1000, 10000]
    times = []

    for n in sizes:
        if "stack" in problem_id:
            setup = f"s = Stack()\nfor i in range({n}): s.push(i)"
            call = f"s.pop()"
        else:
            setup = f"data = list(range({n}))"
            call = f"len(data)"

        harness = f"""
import time as _time
{setup}
_runs = []
for _ in range(3):
    _t0 = _time.perf_counter()
    {call}
    _t1 = _time.perf_counter()
    _runs.append(_t1 - _t0)
print(sorted(_runs)[1])
"""
        full = code + "\n" + harness
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(full)
            tmp = f.name
        try:
            res = subprocess.run(["python", tmp], capture_output=True, text=True, timeout=10)
            val = float(res.stdout.strip()) if res.stdout.strip() else None
        except Exception:
            val = None
        finally:
            os.unlink(tmp)
        times.append(val)

    if None in times or times[0] == 0:
        return "O(1)"

    ratios = []
    for i in range(1, len(sizes)):
        if times[i - 1] and times[i - 1] > 0:
            ratios.append(times[i] / times[i - 1])

    if not ratios:
        return "O(1)"

    avg_ratio = sum(ratios) / len(ratios)
    size_ratio = sizes[1] / sizes[0]  # 10x

    if avg_ratio < 1.5:
        return "O(1)"
    elif avg_ratio < size_ratio * 0.5:
        return "O(log n)"
    elif avg_ratio < size_ratio * 1.5:
        return "O(n)"
    elif avg_ratio < size_ratio * math.log(size_ratio) * 1.5:
        return "O(n log n)"
    elif avg_ratio < size_ratio ** 2 * 1.5:
        return "O(n²)"
    else:
        return "O(n³)"


def check_quality(code: str) -> dict:
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
        f.write(code)
        tmp = f.name

    linter_score = 0.0
    try:
        res = subprocess.run(
            ["pylint", tmp, "--output-format=json", "--score=yes"],
            capture_output=True, text=True, timeout=15
        )
        # Parse score from text output
        for line in res.stdout.splitlines():
            if "Your code has been rated at" in line:
                parts = line.split("rated at")
                if len(parts) > 1:
                    score_part = parts[1].strip().split("/")[0].strip()
                    try:
                        linter_score = float(score_part)
                    except ValueError:
                        pass
                break
        # Also try JSON
        try:
            messages = json.loads(res.stdout)
        except Exception:
            messages = []
    except Exception:
        messages = []
    finally:
        os.unlink(tmp)

    lines = code.splitlines()
    num_functions = sum(1 for line in lines if line.strip().startswith("def "))
    max_function_length = 0
    current_length = 0
    in_function = False
    for line in lines:
        if line.strip().startswith("def "):
            in_function = True
            current_length = 1
        elif in_function:
            if line and not line[0].isspace() and not line.strip().startswith("#"):
                max_function_length = max(max_function_length, current_length)
                in_function = False
                current_length = 0
            else:
                current_length += 1
    if in_function:
        max_function_length = max(max_function_length, current_length)

    if linter_score >= 9:
        grade = "A"
    elif linter_score >= 7:
        grade = "B"
    elif linter_score >= 5:
        grade = "C"
    else:
        grade = "D"

    return {
        "linter_score": linter_score,
        "num_functions": num_functions,
        "max_function_length": max_function_length,
        "quality_grade": grade,
    }


_COMPLEXITY_ORDER = ["O(1)", "O(log n)", "O(n)", "O(n log n)", "O(n²)", "O(n³)"]


def _complexity_gap(actual: str, expected: str) -> int:
    try:
        ai = _COMPLEXITY_ORDER.index(actual)
        ei = _COMPLEXITY_ORDER.index(expected)
        return max(0, ai - ei)
    except ValueError:
        return 3


def compute_scores(test_results: list, hidden_results: list, complexity_class: str, expected_complexity: str, quality: dict) -> dict:
    total_visible = len(test_results)
    passing_visible = sum(1 for r in test_results if r.get("passed"))
    correctness = (passing_visible / total_visible * 100) if total_visible else 0

    gap = _complexity_gap(complexity_class, expected_complexity)
    if gap == 0:
        complexity = 100
    elif gap == 1:
        complexity = 60
    elif gap == 2:
        complexity = 20
    else:
        complexity = 0

    quality_score = max(0, min(100, quality["linter_score"] * 10))

    total_hidden = len(hidden_results)
    passing_hidden = sum(1 for r in hidden_results if r.get("passed"))
    robustness = (passing_hidden / total_hidden * 100) if total_hidden else 0

    total = (
        correctness * 0.40
        + complexity * 0.20
        + quality_score * 0.20
        + robustness * 0.10
    )

    return {
        "correctness_score": round(correctness, 1),
        "complexity_score": round(complexity, 1),
        "quality_score": round(quality_score, 1),
        "robustness_score": round(robustness, 1),
        "total_score": round(total, 1),
    }
