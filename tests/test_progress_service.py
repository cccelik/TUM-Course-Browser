from app.schemas import CategoryProgress


def test_category_progress_shape():
    item = CategoryProgress(
        category_id=1,
        title="Theory",
        required_credits=15.0,
        passed_credits=21.0,
        wanted_credits=6.0,
        remaining_credits=0.0,
        fulfilled=True,
        progress_percent=100.0,
        notes=None,
    )
    assert item.fulfilled is True
    assert item.progress_percent == 100.0
