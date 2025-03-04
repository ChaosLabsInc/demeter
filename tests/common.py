def assert_equal_with_error(a, b, allowed_error=0.0005):
    if a == b == 0:
        return True
    base = a if a != 0 else b
    error = abs((a - b) / base)
    return error < allowed_error


def assert_equal(a, b, msg=""):
    if a != b:
        raise RuntimeError(f"{a} not equal to {b}, {msg}")
