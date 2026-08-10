"""Tests for scraper/logging.py (sinks, configure_logging, correlation_id)."""

from __future__ import annotations

import io
import sys

import scraper.logging as slogging


class _NoBufferStream:
    """Fake stdout without a ``buffer`` attribute."""


class _FakeStdout:
    def __init__(self):
        self.buffer = io.BytesIO()


def test_utf8_stream_write_encodes():
    stream = io.BytesIO()
    sink = slogging._Utf8Stream(stream)
    written = sink.write("Привет, мир!")
    assert written == len("Привет, мир!")
    assert stream.getvalue() == "Привет, мир!".encode()
    sink.flush()
    assert stream.getvalue() == "Привет, мир!".encode()


def test_utf8_stream_write_closed_buffer_suppressed():
    stream = io.BytesIO()
    sink = slogging._Utf8Stream(stream)
    stream.close()
    assert sink.write("data") == 4
    sink.flush()


def test_stdout_sink_with_buffer_wraps(monkeypatch):
    fake = _FakeStdout()
    monkeypatch.setattr(sys, "stdout", fake)
    sink = slogging._stdout_sink()
    assert isinstance(sink, slogging._Utf8Stream)
    assert sink._buffer is fake.buffer


def test_stdout_sink_without_buffer_returns_stream(monkeypatch):
    fake = _NoBufferStream()
    monkeypatch.setattr(sys, "stdout", fake)
    assert slogging._stdout_sink() is fake


def test_configure_logging_json_twice(monkeypatch):
    monkeypatch.setattr(slogging, "_configured", False)
    monkeypatch.setenv("LOG_FORMAT", "true")
    slogging.configure_logging()
    assert slogging._configured is True
    slogging.configure_logging()


def test_configure_logging_plain_format(monkeypatch):
    monkeypatch.setattr(slogging, "_configured", False)
    monkeypatch.setenv("LOG_FORMAT", "false")
    slogging.configure_logging()
    assert slogging._configured is True


def test_get_logger_bound(monkeypatch):
    from loguru import logger as global_logger

    monkeypatch.setattr(slogging, "_configured", True)
    logger = slogging.get_logger("my.module")
    assert isinstance(logger, type(global_logger))
    assert slogging.get_logger() is not None


def test_correlation_id_format():
    cid = slogging.correlation_id()
    assert len(cid) == 12
    assert cid.isalnum()
    assert slogging.correlation_id() != slogging.correlation_id()
