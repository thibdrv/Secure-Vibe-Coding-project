import pytest
from customer_insights import analysis


def test_placeholder():
    with pytest.raises(NotImplementedError):
        analysis.cancellation_rate([])
