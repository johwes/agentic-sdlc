# Technical Specification: Integer Addition

## 1. Interface Signature
```python
def add(a: int, b: int) -> int:
    """Returns the sum of two integers."""
```

## 2. Invariants & Contract
- Function must be located in `src/app.py`.
- Must return `a + b` with exact integer arithmetic.
- Verified by pytest suite in `tests/test_spec.py`.
