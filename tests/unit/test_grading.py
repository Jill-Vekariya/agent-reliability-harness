import pytest

from agent_reliability.evaluation.grading import compare_rows, same_cell


@pytest.mark.parametrize(
    "a,b,expected",
    [
        ([[1], [1]], [[1], [1]], True),
        ([[1], [1]], [[1], [2]], False),
        ([[2], [1]], [[1], [2]], True),
        ([[None]], [[""]], False),
        ([[0]], [[False]], False),
        ([["1"]], [[1]], False),
        ([[1.0]], [[1]], False),
        ([], [], True),
        ([[float("inf")]], [[float("inf")]], False),
    ],
)
def test_multisets(a, b, expected):
    assert compare_rows(a, b) is expected


def test_order_tolerance_and_non_greedy_assignment():
    assert not compare_rows([[2], [1]], [[1], [2]], ordered=True)
    assert compare_rows([[0.1], [0.0]], [[0.0], [0.2]], atol=0.11, tolerant_columns=[0])
    assert same_cell(1.0, 1, tolerant=True)
    assert not same_cell(float("nan"), float("nan"), tolerant=True)
    assert not compare_rows([[1, 2]], [[1]])
