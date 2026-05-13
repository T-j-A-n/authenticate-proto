import subprocess
import tempfile
import os
import time


def run_code(code: str, test_cases: list[dict]) -> dict:
    harness_lines = []
    for tc in test_cases:
        name = tc["name"]
        setup = tc.get("setup", "")
        call = tc["call"]
        expected = tc["expected"]

        # Special-case tests that expect an exception
        if expected in ("IndexError", "ValueError", "TypeError", "KeyError"):
            harness_lines.append(f"""
try:
{chr(10).join('    ' + line for line in setup.splitlines())}
    try:
        {call}
        print("TEST:{name}:FAIL:no exception raised")
    except {expected}:
        print("TEST:{name}:PASS:{expected} raised")
    except Exception as _e:
        print(f"TEST:{name}:FAIL:wrong exception {{_e}}")
except Exception as _outer:
    print(f"TEST:{name}:ERROR:{{_outer}}")
""")
        else:
            harness_lines.append(f"""
try:
{chr(10).join('    ' + line for line in setup.splitlines())}
    _result = {call}
    _expected = {expected}
    if str(_result) == str(_expected):
        print(f"TEST:{name}:PASS:{{_result}}")
    else:
        print(f"TEST:{name}:FAIL:got {{_result!r}} expected {{_expected!r}}")
except Exception as _e:
    print(f"TEST:{name}:ERROR:{{_e}}")
""")

    full_code = code + "\n" + "\n".join(harness_lines)

    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
        f.write(full_code)
        tmppath = f.name

    try:
        start = time.time()
        result = subprocess.run(
            ["python", tmppath],
            capture_output=True,
            text=True,
            timeout=5,
        )
        runtime_ms = int((time.time() - start) * 1000)
    except subprocess.TimeoutExpired:
        return {"results": [{"test_name": tc["name"], "passed": False, "stdout": "", "stderr": "Timeout"} for tc in test_cases], "runtime_ms": 5000}
    finally:
        os.unlink(tmppath)

    results = []
    parsed_names = set()
    for line in result.stdout.splitlines():
        if line.startswith("TEST:"):
            parts = line.split(":", 3)
            if len(parts) >= 3:
                _, name, status, *rest = parts
                detail = rest[0] if rest else ""
                results.append({
                    "test_name": name,
                    "passed": status == "PASS",
                    "stdout": detail,
                    "stderr": result.stderr[:500] if status == "ERROR" else "",
                })
                parsed_names.add(name)

    # Tests that didn't produce output (e.g., crashed before running)
    for tc in test_cases:
        if tc["name"] not in parsed_names:
            results.append({
                "test_name": tc["name"],
                "passed": False,
                "stdout": "",
                "stderr": result.stderr[:500],
            })

    return {"results": results, "runtime_ms": runtime_ms}
