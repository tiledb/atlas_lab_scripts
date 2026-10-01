"""Detect, track, and gate DBQ_Mk6.py processes for the TileQA web UI."""

from __future__ import annotations

import os
import signal
import subprocess
import threading
import time
from collections import deque
from datetime import datetime, timezone
from pathlib import Path

SCRIPT_MARKER = 'DBQ_Mk6.py'
MAX_OUTPUT_CHARS = 200_000


def format_duration(seconds):
    if seconds is None:
        return None
    try:
        total = max(0, int(seconds))
    except (TypeError, ValueError):
        return None
    hours, rem = divmod(total, 3600)
    minutes, secs = divmod(rem, 60)
    if hours:
        return f'{hours}h {minutes}m {secs}s'
    if minutes:
        return f'{minutes}m {secs}s'
    return f'{secs}s'


def parse_id_spec(value):
    """Parse '1,3,10-12' style IDs into a sorted unique list. Empty -> []."""
    text = str(value or '').strip()
    if not text:
        return []
    ids = []
    for token in text.replace(';', ',').split(','):
        token = token.strip()
        if not token:
            continue
        if '-' in token:
            ends = token.split('-', 1)
            try:
                start = int(ends[0].strip())
                end = int(ends[1].strip())
            except ValueError as exc:
                raise ValueError(f'Invalid id range "{token}"') from exc
            if end < start:
                start, end = end, start
            ids.extend(range(start, end + 1))
        else:
            ids.append(int(token))
    seen = set()
    ordered = []
    for item in ids:
        if item not in seen:
            seen.add(item)
            ordered.append(item)
    return ordered


def _extract_flag_value(command, flags):
    """Return the value after the first matching CLI flag, or None."""
    if not command:
        return None
    tokens = str(command).split()
    flag_set = set(flags)
    for index, token in enumerate(tokens):
        if token in flag_set:
            if index + 1 < len(tokens):
                nxt = tokens[index + 1]
                if nxt.startswith('-'):
                    return ''
                return nxt
            return ''
        for flag in flags:
            prefix = f'{flag}='
            if token.startswith(prefix):
                return token[len(prefix):]
    return None


def parse_dbq_scope(command):
    """
    Extract benchtest / daughterboard constraints from a DBQ command string.

    Missing -b and -d means unrestricted (whole script scope).
    """
    bench_raw = _extract_flag_value(command, ('-b', '--benchtest_id'))
    board_raw = _extract_flag_value(command, ('-d', '--daughterboard_id'))
    try:
        benchtests = parse_id_spec(bench_raw) if bench_raw not in (None, '') else None
    except ValueError:
        benchtests = None
    try:
        daughterboards = parse_id_spec(board_raw) if board_raw not in (None, '') else None
    except ValueError:
        daughterboards = None

    # Flag present with empty/invalid value: treat as unconstrained on that axis.
    if bench_raw == '':
        benchtests = None
    if board_raw == '':
        daughterboards = None

    unrestricted = benchtests is None and daughterboards is None
    return {
        'benchtests': benchtests,
        'daughterboards': daughterboards,
        'unrestricted': unrestricted,
        'benchtest_label': (
            'all' if benchtests is None else ','.join(str(item) for item in benchtests)
        ),
        'daughterboard_label': (
            'all' if daughterboards is None else ','.join(str(item) for item in daughterboards)
        ),
    }


def _sets_intersect(left, right):
    if not left or not right:
        return False
    right_set = set(right)
    return any(item in right_set for item in left)


def scopes_overlap(left, right):
    """
    True when two DBQ scopes collide.

    - Either unrestricted (no -b and no -d) overlaps everything.
    - Otherwise overlap only if both constrain benchtests and those IDs intersect,
      or both constrain daughterboards and those IDs intersect.
    """
    if not left or not right:
        return True
    if left.get('unrestricted') or right.get('unrestricted'):
        return True
    left_bt = left.get('benchtests')
    right_bt = right.get('benchtests')
    left_db = left.get('daughterboards')
    right_db = right.get('daughterboards')
    if left_bt is not None and right_bt is not None and _sets_intersect(left_bt, right_bt):
        return True
    if left_db is not None and right_db is not None and _sets_intersect(left_db, right_db):
        return True
    return False


def _process_start_epoch(pid):
    try:
        return Path(f'/proc/{pid}').stat().st_ctime
    except OSError:
        return None


def _read_cmdline(pid):
    try:
        raw = Path(f'/proc/{pid}/cmdline').read_bytes()
        return raw.replace(b'\0', b' ').decode('utf-8', errors='replace').strip()
    except OSError:
        return ''


def _read_process_resources(pid, start_epoch=None, now=None):
    """Return CPU/memory usage for a live process from /proc."""
    now = time.time() if now is None else now
    info = {
        'cpu_percent': None,
        'cpu_time_seconds': None,
        'memory_rss_kb': None,
        'memory_rss_mb': None,
        'memory_percent': None,
    }
    try:
        raw = Path(f'/proc/{pid}/stat').read_text()
        rparen = raw.rfind(')')
        if rparen < 0:
            return info
        fields = raw[rparen + 2:].split()
        # fields[11]=utime, fields[12]=stime (clock ticks)
        utime = int(fields[11])
        stime = int(fields[12])
        try:
            clk = os.sysconf('SC_CLK_TCK') or 100
        except (ValueError, OSError, AttributeError):
            clk = 100
        cpu_seconds = (utime + stime) / float(clk)
        info['cpu_time_seconds'] = round(cpu_seconds, 1)
        elapsed = max((now - start_epoch) if start_epoch else cpu_seconds, 0.001)
        info['cpu_percent'] = round(100.0 * cpu_seconds / elapsed, 1)

        rss_kb = None
        for line in Path(f'/proc/{pid}/status').read_text().splitlines():
            if line.startswith('VmRSS:'):
                parts = line.split()
                if len(parts) >= 2:
                    rss_kb = int(parts[1])
                break
        if rss_kb is not None:
            info['memory_rss_kb'] = rss_kb
            info['memory_rss_mb'] = round(rss_kb / 1024.0, 1)
            mem_total_kb = None
            for line in Path('/proc/meminfo').read_text().splitlines():
                if line.startswith('MemTotal:'):
                    mem_total_kb = int(line.split()[1])
                    break
            if mem_total_kb:
                info['memory_percent'] = round(100.0 * rss_kb / mem_total_kb, 2)
    except (OSError, ValueError, IndexError):
        return info
    return info


def find_dbq_processes(script_path=None):
    """Return live OS processes whose cmdline references DBQ_Mk6.py."""
    script_name = Path(script_path).name if script_path else SCRIPT_MARKER
    results = []
    now = time.time()
    try:
        entries = list(Path('/proc').iterdir())
    except OSError:
        return results

    for entry in entries:
        if not entry.name.isdigit():
            continue
        pid = int(entry.name)
        if pid == os.getpid():
            continue
        cmdline = _read_cmdline(pid)
        if not cmdline:
            continue
        if SCRIPT_MARKER not in cmdline and script_name not in cmdline:
            continue
        start = _process_start_epoch(pid)
        scope = parse_dbq_scope(cmdline)
        resources = _read_process_resources(pid, start_epoch=start, now=now)
        results.append({
            'pid': pid,
            'cmdline': cmdline,
            'started_at_epoch': start,
            'started_at': (
                datetime.fromtimestamp(start, tz=timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')
                if start else None
            ),
            'running_seconds': int(now - start) if start else None,
            'running_for': format_duration(now - start) if start else None,
            'tracked_by_ui': False,
            'scope': scope,
            **resources,
        })
    results.sort(key=lambda item: item.get('started_at_epoch') or 0)
    return results


class DbqProcessManager:
    """Track DBQ_Mk6 runs and expose status/kill/overlap gating for the web UI."""

    def __init__(self, script_path):
        self.script_path = Path(script_path)
        self._lock = threading.RLock()
        self._jobs = {}
        self._job_seq = 0

    def _append_job_output(self, job, text):
        if not text or job is None:
            return
        output = job.setdefault('output', deque())
        job['output_chars'] = int(job.get('output_chars') or 0) + len(text)
        output.append(text)
        while job['output_chars'] > MAX_OUTPUT_CHARS and output:
            removed = output.popleft()
            job['output_chars'] -= len(removed)

    def _job_payload(self, job):
        if not job:
            return None
        now = time.time()
        started = job.get('started_at_epoch')
        return {
            'id': job.get('id'),
            'active': bool(job.get('active')),
            'source': job.get('source'),
            'command': job.get('command'),
            'cmdline': job.get('cmdline'),
            'started_at_epoch': started,
            'started_at': job.get('started_at'),
            'running_seconds': int(now - started) if started else None,
            'running_for': format_duration(now - started) if started else None,
            'pids': list(job.get('pids') or []),
            'scope': job.get('scope') or parse_dbq_scope(job.get('command')),
            'output_tail': ''.join(job.get('output') or []),
            'output_available': bool(job.get('output')),
        }

    def status(self, proposed_command=None):
        with self._lock:
            processes = find_dbq_processes(self.script_path)
            active_jobs = [
                self._job_payload(job)
                for job in self._jobs.values()
                if job.get('active')
            ]
            pid_to_job = {}
            for job in active_jobs:
                for pid in job.get('pids') or []:
                    pid_to_job[pid] = job
                process = self._jobs.get(job['id'], {}).get('process')
                if process is not None and process.poll() is None:
                    pid_to_job[process.pid] = job

            for proc in processes:
                job = pid_to_job.get(proc['pid'])
                if job:
                    proc['tracked_by_ui'] = True
                    proc['source'] = job.get('source')
                    proc['job_id'] = job.get('id')

            running = bool(processes) or bool(active_jobs)
            proposed_scope = parse_dbq_scope(proposed_command) if proposed_command else None
            overlaps = None
            if proposed_scope is not None and running:
                overlaps = False
                for proc in processes:
                    if scopes_overlap(proposed_scope, proc.get('scope') or parse_dbq_scope(proc.get('cmdline'))):
                        overlaps = True
                        break
                if not overlaps:
                    for job in active_jobs:
                        if scopes_overlap(proposed_scope, job.get('scope') or parse_dbq_scope(job.get('command'))):
                            overlaps = True
                            break

            output_tail = None
            if active_jobs:
                # Prefer the newest active job's output for the dialog.
                output_tail = active_jobs[-1].get('output_tail') or None

            return {
                'running': running,
                'processes': processes,
                'jobs': active_jobs,
                'job': active_jobs[-1] if active_jobs else None,
                'output_tail': output_tail,
                'output_available': bool(output_tail),
                'proposed_scope': proposed_scope,
                'overlaps': overlaps,
            }

    def _kill_pid(self, pid):
        try:
            os.killpg(pid, signal.SIGTERM)
            return True
        except ProcessLookupError:
            return False
        except (PermissionError, OSError):
            try:
                os.kill(pid, signal.SIGTERM)
                return True
            except ProcessLookupError:
                return False
            except OSError:
                return False

    def _force_kill_pid(self, pid):
        try:
            os.killpg(pid, signal.SIGKILL)
            return True
        except ProcessLookupError:
            return False
        except (PermissionError, OSError):
            try:
                os.kill(pid, signal.SIGKILL)
                return True
            except Exception:
                return False

    def kill_all(self, timeout=8):
        with self._lock:
            pids = {proc['pid'] for proc in find_dbq_processes(self.script_path)}
            for job in self._jobs.values():
                pids.update(job.get('pids') or [])
                process = job.get('process')
                if process is not None and process.poll() is None:
                    pids.add(process.pid)

            killed = []
            for pid in sorted(pids):
                if self._kill_pid(pid):
                    killed.append(pid)

            deadline = time.time() + timeout
            while time.time() < deadline:
                remaining = find_dbq_processes(self.script_path)
                alive_tracked = any(
                    job.get('process') is not None and job['process'].poll() is None
                    for job in self._jobs.values()
                )
                if not remaining and not alive_tracked:
                    break
                time.sleep(0.15)

            for proc in find_dbq_processes(self.script_path):
                self._force_kill_pid(proc['pid'])
            for job in self._jobs.values():
                process = job.get('process')
                if process is not None and process.poll() is None:
                    try:
                        self._force_kill_pid(process.pid)
                    except Exception:
                        pass
                    try:
                        process.kill()
                    except Exception:
                        pass
                job['process'] = None
                job['active'] = False
                job['ended_at_epoch'] = time.time()
                self._append_job_output(job, '\n[web UI] Existing DBQ_Mk6 instance killed.\n')

            self._jobs = {
                job_id: job
                for job_id, job in self._jobs.items()
                if job.get('active')
            }
            return {
                'success': True,
                'killed_pids': killed,
                'remaining': find_dbq_processes(self.script_path),
            }

    def begin_job(self, source, command, replace=False, allow_parallel=False):
        """
        Start tracking a new DBQ job.

        Returns (conflict_status_or_None, job_id_or_None).
        """
        with self._lock:
            current = self.status(proposed_command=command)
            if current['running'] and not replace and not allow_parallel:
                return current, None
            if current['running'] and allow_parallel and not replace:
                if current.get('overlaps') is not False:
                    # Overlap or unknown: refuse parallel start.
                    current = dict(current)
                    current['parallel_blocked'] = True
                    return current, None
            if current['running'] and replace:
                self.kill_all()

            self._job_seq += 1
            job_id = self._job_seq
            self._jobs[job_id] = {
                'id': job_id,
                'active': True,
                'source': source,
                'command': command,
                'started_at_epoch': time.time(),
                'started_at': datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC'),
                'pids': [],
                'process': None,
                'output': deque(),
                'output_chars': 0,
                'scope': parse_dbq_scope(command),
                'allow_parallel': bool(allow_parallel),
            }
            return None, job_id

    def end_job(self, job_id=None):
        with self._lock:
            if job_id is None:
                active = [job for job in self._jobs.values() if job.get('active')]
                if not active:
                    return
                job_id = active[-1]['id']
            job = self._jobs.get(job_id)
            if not job:
                return
            job['active'] = False
            job['ended_at_epoch'] = time.time()
            job['process'] = None
            # Drop finished jobs to keep status tidy.
            self._jobs.pop(job_id, None)

    def iter_tracked_subprocess(self, cmd, cwd, env, job_id=None):
        """Run a subprocess under a tracked job, buffering console output."""
        process = subprocess.Popen(
            cmd,
            cwd=cwd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            env=env,
            start_new_session=True,
        )
        with self._lock:
            if job_id is None:
                active = [job for job in self._jobs.values() if job.get('active')]
                job = active[-1] if active else None
                job_id = job['id'] if job else None
            else:
                job = self._jobs.get(job_id)
            if job is not None:
                job['process'] = process
                pids = list(job.get('pids') or [])
                if process.pid not in pids:
                    pids.append(process.pid)
                job['pids'] = pids
                job['cmdline'] = ' '.join(str(part) for part in cmd)
                job['scope'] = parse_dbq_scope(job['cmdline'])

        try:
            for line in process.stdout:
                with self._lock:
                    job = self._jobs.get(job_id) if job_id is not None else None
                    self._append_job_output(job, line)
                yield line
        except GeneratorExit:
            try:
                os.killpg(process.pid, signal.SIGTERM)
            except Exception:
                process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except Exception:
                    process.kill()
                process.wait()
            raise

        code = process.wait()
        with self._lock:
            job = self._jobs.get(job_id) if job_id is not None else None
            if job is not None and job.get('process') is process:
                job['process'] = None
        yield {'__returncode__': code}


_MANAGER = None
_MANAGER_LOCK = threading.Lock()


def get_dbq_process_manager(script_path):
    global _MANAGER
    with _MANAGER_LOCK:
        if _MANAGER is None:
            _MANAGER = DbqProcessManager(script_path)
        return _MANAGER
