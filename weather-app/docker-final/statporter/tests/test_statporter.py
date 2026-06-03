from unittest.mock import MagicMock, patch

import statporter


def _stats(cpu_total, precpu_total, sys_now, sys_prev, ncpu=2):
    return {
        "cpu_stats": {
            "cpu_usage": {
                "total_usage": cpu_total,
                "percpu_usage": [0] * ncpu,
            },
            "system_cpu_usage": sys_now,
        },
        "precpu_stats": {
            "cpu_usage": {"total_usage": precpu_total},
            "system_cpu_usage": sys_prev,
        },
    }


def _minimal_stats():
    return {
        "cpu_stats": {
            "cpu_usage": {"total_usage": 200, "percpu_usage": [100, 100]},
            "system_cpu_usage": 1000,
        },
        "precpu_stats": {
            "cpu_usage": {"total_usage": 100},
            "system_cpu_usage": 900,
        },
        "memory_stats": {"usage": 1024 * 1024, "limit": 8 * 1024 * 1024},
        "networks": {"eth0": {"rx_bytes": 100, "tx_bytes": 50}},
        "blkio_stats": {"io_service_bytes_recursive": []},
    }


def _fake_container(name):
    c = MagicMock()
    c.name = name
    c.short_id = name[:12]
    c.stats.return_value = _minimal_stats()
    return c


class TestStatporterCollector:
    def test_statporter_cpu_percent_normal_delta(self):
        s = _stats(cpu_total=200, precpu_total=100, sys_now=1000, sys_prev=900, ncpu=2)
        result = statporter._cpu_percent(s)
        assert result == (100 / 100) * 2 * 100.0

    def test_statporter_cpu_percent_zero_when_system_usage_missing(self):
        s = _stats(100, 0, None, None)
        assert statporter._cpu_percent(s) == 0.0

    def test_statporter_cpu_percent_zero_when_system_delta_nonpos(self):
        s = _stats(200, 100, 900, 900)
        assert statporter._cpu_percent(s) == 0.0

    def test_statporter_cpu_percent_zero_when_cpu_delta_nonpos(self):
        s = _stats(100, 100, 1000, 900)
        assert statporter._cpu_percent(s) == 0.0

    def test_statporter_cpu_percent_uses_percpu_count(self):
        s = _stats(cpu_total=200, precpu_total=100, sys_now=1000, sys_prev=900, ncpu=4)
        result = statporter._cpu_percent(s)
        assert result == (100 / 100) * 4 * 100.0

    def test_statporter_blkio_sums_read_and_write(self):
        s = {
            "blkio_stats": {
                "io_service_bytes_recursive": [
                    {"op": "Read", "value": 10},
                    {"op": "Write", "value": 5},
                ]
            }
        }
        assert statporter._blkio_bytes(s) == (10, 5)

    def test_statporter_blkio_handles_missing_recursive(self):
        assert statporter._blkio_bytes({"blkio_stats": {}}) == (0, 0)
        assert statporter._blkio_bytes(
            {"blkio_stats": {"io_service_bytes_recursive": None}}
        ) == (0, 0)

    def test_statporter_blkio_op_is_case_insensitive(self):
        s = {
            "blkio_stats": {
                "io_service_bytes_recursive": [
                    {"op": "READ", "value": 20},
                    {"op": "WRITE", "value": 8},
                ]
            }
        }
        assert statporter._blkio_bytes(s) == (20, 8)

    def test_statporter_scrape_one_converts_hyphen_to_underscore(self):
        container = _fake_container("demo-container")
        result = statporter._scrape_one(container)
        assert result is not None
        name, _ = result
        assert name == "demo_container"

    def test_statporter_scrape_one_returns_none_on_error(self):
        container = _fake_container("demo-container")
        container.stats.side_effect = Exception("docker error")
        assert statporter._scrape_one(container) is None

    def test_statporter_stale_label_removed_when_container_gone(self, monkeypatch):
        monkeypatch.setattr(statporter, "_seen_names", set())
        mock_client = MagicMock()
        monkeypatch.setattr(statporter, "get_client", lambda: mock_client)

        mock_client.containers.list.return_value = [
            _fake_container("demo-container"),
            _fake_container("weather-app"),
        ]
        statporter.collect_metrics()

        mock_client.containers.list.return_value = [_fake_container("weather-app")]
        with patch.object(statporter.CPU_PERCENT, "remove") as mock_remove:
            statporter.collect_metrics()

        mock_remove.assert_called_with("demo_container")

    def test_statporter_seen_names_tracks_current_round(self, monkeypatch):
        monkeypatch.setattr(statporter, "_seen_names", set())
        mock_client = MagicMock()
        mock_client.containers.list.return_value = [
            _fake_container("demo-container"),
            _fake_container("weather-app"),
        ]
        monkeypatch.setattr(statporter, "get_client", lambda: mock_client)

        statporter.collect_metrics()

        assert statporter._seen_names == {"demo_container", "weather_app"}
