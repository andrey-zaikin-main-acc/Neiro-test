from app.services.metrics import measure_wall_clock


def test_measure_wall_clock_records_seconds():
    with measure_wall_clock() as metric:
        sum(range(100))
    assert metric.seconds >= 0
