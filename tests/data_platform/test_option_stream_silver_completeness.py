def test_silver_check_imports():
    from scripts.migration.check_option_stream_silver_completeness import (
        SILVER_COMMAND,
        SILVER_VERSION,
    )

    assert SILVER_VERSION
    assert SILVER_COMMAND
