from __future__ import annotations

import gc
import os
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs

import pytest

import finiq.data_scraper.core.client as client_module
from finiq.data_scraper.core.client import download_pages


def _result_page_html(page_number: int, page_size: int, total_pages: int) -> bytes:
    total_items = page_size * total_pages
    rows = []
    for row_index in range(page_size):
        item_no = ((page_number - 1) * page_size) + row_index + 1
        rows.append(
            f"""
            <tr>
              <td>{item_no}</td>
              <td>2026-01-01 09:00</td>
              <td><a id="companysum" title="회사{item_no}" onclick="companysummary_open('{item_no:06d}')">회사</a></td>
              <td><a title="공시 {item_no}" onclick="openDisclsViewer('202601{item_no:08d}','')">공시</a></td>
              <td>제출인</td>
            </tr>
            """
        )
    return (
        f"""
        <html><body>
          <section class="paging-group"><div class="paging type-00">
            전체 <em>{total_items}</em>건 : <strong>{page_number}</strong>/{total_pages}
          </div></section>
          <table class="list"><tbody>{''.join(rows)}</tbody></table>
        </body></html>
        """
    ).encode("utf-8")


class _KindHandler(BaseHTTPRequestHandler):
    total_pages = 200
    fail_pages: set[int] = set()
    delay_seconds = 0.0

    def log_message(self, _format: str, *_args) -> None:
        return

    def _send(self, status: int, content: bytes) -> None:
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def do_GET(self) -> None:
        self._send(200, b"<html><body>main</body></html>")

    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length") or 0)
        form = parse_qs(self.rfile.read(length).decode("utf-8"))
        page_number = int(form["pageIndex"][0])
        page_size = int(form["currentPageSize"][0])
        if self.delay_seconds:
            time.sleep(self.delay_seconds)
        if page_number in self.fail_pages:
            self._send(500, b"server error")
            return
        self._send(
            200,
            _result_page_html(page_number, page_size, self.total_pages),
        )


@pytest.fixture
def local_kind_server(monkeypatch: pytest.MonkeyPatch):
    _KindHandler.fail_pages = set()
    _KindHandler.delay_seconds = 0.0
    server = ThreadingHTTPServer(("127.0.0.1", 0), _KindHandler)
    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()
    origin = f"http://127.0.0.1:{server.server_port}"
    monkeypatch.setattr(client_module, "KIND_SEARCH_PAGE_URL", f"{origin}/main")
    monkeypatch.setattr(client_module, "KIND_SEARCH_RESULTS_URL", f"{origin}/results")
    try:
        yield server
    finally:
        server.shutdown()
        server.server_close()
        server_thread.join(timeout=2)


def _rss_kib() -> int:
    result = subprocess.run(
        ["ps", "-o", "rss=", "-p", str(os.getpid())],
        check=True,
        capture_output=True,
        text=True,
    )
    return int(result.stdout.strip())


def _download_range(output_directory: Path, *, pages: int, workers: int) -> None:
    _KindHandler.total_pages = pages
    download_pages(
        output_directory=output_directory,
        request_headers={"User-Agent": "FINIQ runtime stress test"},
        start_date="2026-01-01",
        end_date="2026-01-01",
        start_page=1,
        end_page=pages,
        page_size=1,
        wait_seconds_between_requests=0,
        timeout=3,
        max_workers=workers,
    )


def test_parallel_download_repeated_runs_do_not_accumulate_resources(
    tmp_path: Path, local_kind_server
) -> None:
    _download_range(tmp_path / "warmup", pages=20, workers=8)
    gc.collect()
    baseline_rss = _rss_kib()
    baseline_fds = len(os.listdir("/dev/fd"))

    for round_index in range(5):
        _download_range(tmp_path / f"round-{round_index}", pages=200, workers=8)

    gc.collect()
    time.sleep(0.1)
    final_rss = _rss_kib()
    final_fds = len(os.listdir("/dev/fd"))
    live_worker_threads = [
        thread.name
        for thread in threading.enumerate()
        if thread.name.startswith("ThreadPoolExecutor-")
    ]
    print(
        f"runtime_resource_delta rss_kib={final_rss - baseline_rss} "
        f"fds={final_fds - baseline_fds} workers={len(live_worker_threads)}"
    )

    assert final_rss - baseline_rss < 40 * 1024
    assert final_fds <= baseline_fds + 4
    assert live_worker_threads == []


def test_parallel_download_closes_workers_after_http_failure(
    tmp_path: Path, local_kind_server
) -> None:
    _KindHandler.fail_pages = {7}
    baseline_fds = len(os.listdir("/dev/fd"))

    with pytest.raises(Exception, match="500 Server Error"):
        _download_range(tmp_path / "failure", pages=100, workers=8)

    gc.collect()
    time.sleep(0.1)
    assert len(os.listdir("/dev/fd")) <= baseline_fds + 4
    assert not any(
        thread.name.startswith("ThreadPoolExecutor-")
        for thread in threading.enumerate()
    )


def test_parallel_download_stops_submitting_after_cancellation(
    tmp_path: Path, local_kind_server
) -> None:
    _KindHandler.delay_seconds = 0.02
    cancelled = threading.Event()
    timer = threading.Timer(0.12, cancelled.set)
    timer.start()
    try:
        download_pages(
            output_directory=tmp_path / "cancelled",
            request_headers={"User-Agent": "FINIQ runtime cancellation test"},
            start_date="2026-01-01",
            end_date="2026-01-01",
            start_page=1,
            end_page=200,
            page_size=1,
            wait_seconds_between_requests=0,
            timeout=3,
            max_workers=8,
            cancel_check=cancelled.is_set,
        )
    finally:
        timer.cancel()

    saved_pages = list((tmp_path / "cancelled").glob("*_post_page_*.body"))
    assert cancelled.is_set()
    assert 0 < len(saved_pages) < 200
    assert not any(
        thread.name.startswith("ThreadPoolExecutor-")
        for thread in threading.enumerate()
    )
