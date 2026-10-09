"""Zamanlanmış görevler (APScheduler): ölçüm, gece uyarı kontrolü, keşif, bildirim gönderimi.

Ayarlar (ölçüm aralığı, kontrol saati, keşif aralığı) yönetici tarafından değiştirilince en geç
bir dakika içinde zamanlamaya yansır. Uygulama kapalıyken kaçan gece kontrolü, açılışta
telafi edilir. İşler tek çalıştırıcıdır (aynı iş üst üste binmez).
"""

from __future__ import annotations

import asyncio
import logging
import os
import sqlite3
import sys
from collections.abc import Awaitable, Callable
from datetime import datetime, timedelta
from pathlib import Path
from typing import IO, Any

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from . import config, db, maintenance, notify, radar, refresh, settings, strikes
from .clock import now_utc, to_iso
from .collectors import BrowserCollector
from .notify import Sender

log = logging.getLogger("etkilesim.scheduler")
BrowserFactory = Callable[[], Any]


def last_scheduled(local_now: datetime, hhmm: str) -> datetime:
    """`local_now` anına göre en son geçmiş 'HH:MM' tetik zamanı."""
    hour, minute = (int(part) for part in hhmm.split(":"))
    candidate = local_now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    return candidate if candidate <= local_now else candidate - timedelta(days=1)


def _job_started(conn: sqlite3.Connection, name: str, now: datetime) -> int:
    cur = conn.execute("INSERT INTO job_runs(name, started_at) VALUES (?,?)", (name, to_iso(now)))
    return int(cur.lastrowid or 0)


def _job_finished(conn: sqlite3.Connection, job_id: int, ok: bool, detail: str, now: datetime) -> None:
    conn.execute(
        "UPDATE job_runs SET status=?, finished_at=?, detail=? WHERE id=?",
        ("ok" if ok else "error", to_iso(now), detail[:500], job_id),
    )


def strike_check_overdue(conn: sqlite3.Connection, local_now: datetime) -> bool:
    """Son zamanlanmış gece kontrolünden beri başarılı bir kontrol yoksa True (açılışta telafi)."""
    due = last_scheduled(local_now, str(settings.get(conn, "strike_check_time")))
    row = conn.execute(
        "SELECT 1 FROM job_runs WHERE name='strike_check' AND status='ok' AND started_at >= ?",
        (to_iso(due),),
    ).fetchone()
    return row is None


class EngineScheduler:
    def __init__(
        self,
        db_file: Path,
        sender: Sender | None = None,
        browser_factory: BrowserFactory | None = None,
    ) -> None:
        self._db_file = db_file
        self._sender = sender
        self._browser_factory = browser_factory
        self._scheduler = AsyncIOScheduler()
        self._applied: dict[str, Any] = {}
        self._startup_tasks: list[asyncio.Task[None]] = []

    def _connect(self) -> sqlite3.Connection:
        return db.connect(self._db_file)

    async def _tracked(self, name: str, work: Callable[[sqlite3.Connection], Awaitable[str]]) -> None:
        conn = self._connect()
        try:
            job_id = _job_started(conn, name, now_utc())
            try:
                detail = await work(conn)
                _job_finished(conn, job_id, True, detail, now_utc())
                log.info("iş tamamlandı: %s (%s)", name, detail, extra={"job_id": job_id})
            except Exception as exc:
                _job_finished(conn, job_id, False, f"{exc.__class__.__name__}: {exc}", now_utc())
                log.exception("iş başarısız: %s", name, extra={"job_id": job_id})
        finally:
            conn.close()

    async def run_refresh(self) -> None:
        async def work(conn: sqlite3.Connection) -> str:
            headless = bool(settings.get(conn, "scrape_headless"))
            factory = self._browser_factory or (
                lambda: BrowserCollector(config.profile_dir(), headless=headless)
            )
            summary = await refresh.refresh(conn, browser_factory=factory)
            return str(summary.as_dict())

        await self._tracked("refresh", work)

    async def run_strike_check(self) -> None:
        async def work(conn: sqlite3.Connection) -> str:
            outcomes = strikes.run_inactivity_check(conn)
            return f"{len(outcomes)} uyarı"

        await self._tracked("strike_check", work)

    async def run_discovery(self) -> None:
        async def work(conn: sqlite3.Connection) -> str:
            if not settings.get(conn, "discovery_enabled"):
                return "kapalı"
            keywords = list(settings.get(conn, "discovery_keywords"))
            report = await asyncio.to_thread(self._discover_threadsafe, keywords)
            return f"{report.added} yeni / {report.found} bulundu"

        await self._tracked("discovery", work)

    def _discover_threadsafe(self, keywords: list[str]) -> radar.DiscoveryReport:
        conn = self._connect()
        try:
            return radar.discover(conn, keywords)
        finally:
            conn.close()

    async def run_maintenance(self) -> None:
        """Günlük: saklama süresi temizliği + veritabanı yedeği (§63, §93)."""

        async def retention(conn: sqlite3.Connection) -> str:
            return str(maintenance.apply_retention(conn))

        async def backup(conn: sqlite3.Connection) -> str:
            return str(maintenance.backup(conn))

        await self._tracked("retention", retention)
        await self._tracked("backup", backup)

    async def run_flush(self) -> None:
        def flush_sync() -> notify.FlushSummary:
            conn = self._connect()
            try:
                return notify.flush(conn, self._sender or notify.build_senders(conn))
            finally:
                conn.close()

        try:
            summary = await asyncio.to_thread(flush_sync)
        except Exception:
            log.exception("bildirim gönderimi başarısız")
            return
        if summary.sent or summary.failed:
            log.info("bildirimler: gönderilen=%s başarısız=%s", summary.sent, summary.failed)

    def reconcile(self) -> None:
        """Ayarlardaki değişiklikleri zamanlamaya uygular."""
        conn = self._connect()
        try:
            desired: dict[str, tuple[str, int | str]] = {
                "refresh": ("interval", int(settings.get(conn, "metrics_interval_hours"))),
                "strike_check": ("cron", str(settings.get(conn, "strike_check_time"))),
                "discovery": ("interval", int(settings.get(conn, "discovery_interval_hours"))),
            }
        finally:
            conn.close()
        handlers = {
            "refresh": self.run_refresh,
            "strike_check": self.run_strike_check,
            "discovery": self.run_discovery,
        }
        for name, spec in desired.items():
            if self._applied.get(name) == spec:
                continue
            kind, value = spec
            trigger: Any = (
                IntervalTrigger(hours=int(value))
                if kind == "interval"
                else CronTrigger(hour=int(str(value)[:2]), minute=int(str(value)[3:]))
            )
            self._scheduler.add_job(
                handlers[name],
                trigger,
                id=name,
                replace_existing=True,
                max_instances=1,
                coalesce=True,
                misfire_grace_time=3600,
            )
            self._applied[name] = spec
            log.info("zamanlama güncellendi: %s=%s", name, spec)

    async def start(self) -> None:
        self.reconcile()
        self._scheduler.add_job(
            self.reconcile, IntervalTrigger(minutes=1), id="reconcile", max_instances=1, coalesce=True
        )
        self._scheduler.add_job(
            self.run_flush, IntervalTrigger(minutes=5), id="flush", max_instances=1, coalesce=True
        )
        self._scheduler.add_job(
            self.run_maintenance, IntervalTrigger(hours=24), id="maintenance", max_instances=1, coalesce=True
        )
        self._scheduler.start()
        conn = self._connect()
        try:
            overdue = strike_check_overdue(conn, datetime.now().astimezone())
        finally:
            conn.close()
        if overdue:
            await self.run_strike_check()  # kapalıyken kaçan gece kontrolünü telafi et
        self._startup_tasks = [asyncio.create_task(self.run_refresh()), asyncio.create_task(self.run_flush())]

    def shutdown(self) -> None:
        if self._scheduler.running:
            self._scheduler.shutdown(wait=False)


# ------------------------------------------------------------------------------- tek örnek kilidi


def acquire_lock(path: Path) -> IO[bytes] | None:
    """Süreç ölünce otomatik bırakılan dosya kilidi; zaten çalışan örnek varsa None."""
    handle = open(path, "a+b")  # noqa: SIM115 - ömür boyu açık tutulur
    try:
        if sys.platform == "win32":
            import msvcrt

            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl

            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        handle.close()
        return None
    return handle


PARENT_ENV = "ETKILESIM_PARENT_PID"
PARENT_CHECK_SECONDS = 10.0


def process_alive(pid: int) -> bool:
    """Süreç hâlâ çalışıyor mu? (psutil gerektirmez)"""
    if pid <= 0:
        return False
    if sys.platform == "win32":
        import ctypes

        kernel32 = ctypes.windll.kernel32
        handle = kernel32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
        if not handle:
            return False
        try:
            code = ctypes.c_ulong()
            if not kernel32.GetExitCodeProcess(handle, ctypes.byref(code)):
                return False
            return code.value == 259  # STILL_ACTIVE
        finally:
            kernel32.CloseHandle(handle)
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


async def watch_parent(pid: int, stop: asyncio.Event, interval: float = PARENT_CHECK_SECONDS) -> None:
    """Masaüstü uygulaması kapanınca zamanlayıcı yetim kalmasın (başlatıcı ara süreçleri olsa bile)."""
    while not stop.is_set():
        if not process_alive(pid):
            log.info("üst süreç (%s) kapandı; zamanlayıcı duruyor", pid)
            stop.set()
            return
        try:
            await asyncio.wait_for(stop.wait(), timeout=interval)
        except TimeoutError:
            continue


async def run_daemon(db_file: Path | None = None, parent_pid: int | None = None) -> int:
    lock = acquire_lock(config.lock_path())
    if lock is None:
        log.warning("başka bir zamanlayıcı zaten çalışıyor")
        return 3
    if parent_pid is None:
        raw = os.environ.get(PARENT_ENV, "")
        parent_pid = int(raw) if raw.isdigit() else None
    scheduler = EngineScheduler(db_file or config.db_path())
    stop = asyncio.Event()
    watcher = asyncio.create_task(watch_parent(parent_pid, stop)) if parent_pid else None
    await scheduler.start()
    log.info("zamanlayıcı başladı")
    try:
        await stop.wait()
    finally:
        scheduler.shutdown()
        if watcher is not None:
            watcher.cancel()
        lock.close()
    return 0
