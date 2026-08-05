import pytest
from src.repository import DataRepository


@pytest.fixture(scope="module")
def repo():
    return DataRepository(data_dir="data")


def test_repository_loaded(repo):
    assert len(repo.orders_by_id) > 0
    assert len(repo.customers_by_id) > 0
    assert len(repo.products_by_id) > 0
    assert len(repo.sellers_by_id) > 0


def test_order_lookup(repo):
    # Test with EC_001 order_id
    order = repo.get_order("9b75cdaf2d85857ef023980e15d01546")
    assert order is not None
    assert order["order_id"] == "9b75cdaf2d85857ef023980e15d01546"


def test_category_translation(repo):
    trans = repo.get_translated_category("perfumaria")
    assert trans == "perfumery"
