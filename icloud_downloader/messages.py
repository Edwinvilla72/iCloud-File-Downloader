"""Local Messages database access. No GUI and no writes to Apple's database."""
import csv
import re
import shutil
import sqlite3
import platform
import tempfile
import time
import io
from PIL import Image
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
try:
    import typedstream
    from typedstream.types.foundation import NSString
except ImportError:
    typedstream = None

def message_text(text, attributed_body):
    """Decode the body as a typedstream, never by slicing binary data as text."""
    if text:
        return text
    if not attributed_body:
        return ""
    if typedstream is None:
        return "[Message text unavailable: install pytypedstream]"
    try:
        body = typedstream.unarchive_from_data(bytes(attributed_body))
        # NSAttributedString's first field is its backing NSString. Ignore
        # attribute dictionaries so links and formatting never become body text.
        if body.clazz.name in (b"NSAttributedString", b"NSMutableAttributedString"):
            value = body.contents[0].values[0]
            if isinstance(value, NSString):
                return value.value
    except Exception:
        pass
    return "[Message text unavailable: unsupported attributedBody]"

# ---------------------------
# Utilities
# ---------------------------
def sanitize_filename(name: str, max_len: int = 120) -> str:
    name = re.sub(r"[\x00-\x1f\\/:*?\"<>|]+", "_", name)
    name = name.strip().strip(".")
    if not name:
        name = "untitled"
    if name.split(".")[0].upper() in {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}:
        name = "_" + name
    if len(name) > max_len:
        name = name[:max_len].rstrip("_").rstrip(".")
    return name

def apple_ns_to_unix(ns_value: int):
    """Convert Apple's (ns or s since 2001-01-01) to datetime UTC."""
    try:
        if ns_value is None:
            return None
        if abs(ns_value) > 1e12:
            seconds = ns_value / 1_000_000_000
        else:
            seconds = ns_value
        unix_seconds = seconds + 978_307_200
        return datetime.fromtimestamp(unix_seconds, timezone.utc)
    except Exception:
        return None

def is_image_file(path: Path) -> bool:
    ext = path.suffix.lower()
    return ext in {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".tif", ".tiff", ".webp"}  # HEIC not shown inline


class MessagesStore:
    def __init__(self, log=lambda message: None):
        self.log = log
        self.messages_db_copy = None
        self._messages_temp = tempfile.TemporaryDirectory(prefix="icloud-messages-")

    def close(self):
        self._messages_temp.cleanup()

    def chats(self):
        path = self.ensure_messages_db_copy()
        with closing(sqlite3.connect(path)) as con:
            return con.execute("""
                SELECT ROWID, COALESCE(NULLIF(display_name, ''), chat_identifier, 'Unknown'), chat_identifier
                FROM chat ORDER BY 2 COLLATE NOCASE
            """).fetchall()

    def page(self, chat_id, offset=0, limit=100):
        if not self.messages_db_copy:
            raise RuntimeError("Load conversations first.")
        with closing(sqlite3.connect(self.messages_db_copy)) as con:
            total = self._get_total_messages_for_chat(con, chat_id)
            rows = self._fetch_messages_chunk(con, chat_id, offset, limit)
            attachments = self._attachments_for_message_ids(con, [r[0] for r in rows])
        prepared = {}
        root = Path.home() / "Library" / "Messages" / "Attachments"
        for mid, items in attachments.items():
            prepared[mid] = []
            for filename, name in items:
                src = Path(filename).expanduser() if filename else None
                if src and not src.is_absolute():
                    src = root / src
                if (not src or not src.is_file()) and name:
                    src = root / name
                thumbnail = None
                if src and src.is_file():
                    if is_image_file(src):
                        try:
                            with Image.open(src) as image:
                                image.thumbnail((260, 220))
                                buffer = io.BytesIO()
                                image.convert("RGB").save(buffer, format="PNG")
                                thumbnail = buffer.getvalue()
                        except Exception:
                            pass
                    prepared[mid].append((str(src), name or src.name, thumbnail))
                else:
                    prepared[mid].append((None, name or "Attachment", None))
        return total, rows, prepared

    def ensure_messages_db_copy(self):
        """Take a WAL-aware snapshot; called only by the Messages worker."""
        if platform.system() != "Darwin":
            raise RuntimeError("Messages is macOS-only.")
        src_db = Path.home() / "Library" / "Messages" / "chat.db"
        dst_db = Path(self._messages_temp.name) / "chat.db"
        deadline = time.monotonic() + 20

        def progress(_status, _remaining, _total):
            if time.monotonic() > deadline:
                raise TimeoutError("Messages database is busy. Wait a moment, then try Load Chats again.")

        # mode=ro prevents accidentally creating or modifying Apple's database.
        with closing(sqlite3.connect(src_db.as_uri() + "?mode=ro", uri=True, timeout=5)) as source:
            with closing(sqlite3.connect(dst_db)) as target:
                source.backup(target, pages=256, progress=progress, sleep=0.05)
        self.messages_db_copy = str(dst_db)
        return self.messages_db_copy

    def _get_total_messages_for_chat(self, con, chat_rowid: int) -> int:
        cur = con.cursor()
        cur.execute("""
            SELECT COUNT(*)
            FROM message m
            JOIN chat_message_join cmj ON cmj.message_id = m.ROWID
            WHERE cmj.chat_id = ?;
        """, (chat_rowid,))
        return cur.fetchone()[0] or 0

    def _fetch_messages_chunk(self, con, chat_rowid: int, offset: int, limit: int):
        """Fetch messages newest-first with offset/limit, then reverse to display ascending."""
        cur = con.cursor()
        cur.execute("""
            SELECT
                m.ROWID,
                m.date,
                m.is_from_me,
                COALESCE(h.id, '') as handle_id,
                m.text, m.attributedBody
            FROM message m
            JOIN chat_message_join cmj ON cmj.message_id = m.ROWID
            LEFT JOIN handle h ON h.ROWID = m.handle_id
            WHERE cmj.chat_id = ?
            ORDER BY m.date DESC, m.ROWID DESC
            LIMIT ? OFFSET ?;
        """, (chat_rowid, limit, offset))
        rows = cur.fetchall()
        rows.reverse()  # display ascending
        return [(*row[:4], message_text(row[4], row[5])) for row in rows]

    def _attachments_for_message_ids(self, con, msg_ids):
        if not msg_ids:
            return {}
        cur = con.cursor()
        q_marks = ",".join("?" for _ in msg_ids)
        cur.execute(f"""
            SELECT
                maj.message_id,
                a.filename,
                a.transfer_name
            FROM message_attachment_join maj
            JOIN attachment a ON a.ROWID = maj.attachment_id
            WHERE maj.message_id IN ({q_marks});
        """, msg_ids)
        result = {}
        for mid, filename, transfer_name in cur.fetchall():
            result.setdefault(mid, []).append((filename, transfer_name))
        return result

    def _export_chat_by_rowid(self, chat_rowid: int, chat_display: str, directory: str, log=None):
        log = log or self.log
        if not self.messages_db_copy:
            db_path = self.ensure_messages_db_copy()
            if not db_path:
                return
        chat_name = sanitize_filename(chat_display) or f"chat_{chat_rowid}"
        base_dir = Path(directory) / "Messages" / chat_name
        attachments_dir = base_dir / "attachments"
        base_dir.mkdir(parents=True, exist_ok=True)
        attachments_dir.mkdir(parents=True, exist_ok=True)

        with closing(sqlite3.connect(self.messages_db_copy)) as con:
            cur = con.cursor()
            cur.execute("""
                SELECT m.ROWID, m.date, m.is_from_me, COALESCE(h.id, ''), m.text, m.attributedBody
                FROM message m
                JOIN chat_message_join cmj ON cmj.message_id = m.ROWID
                LEFT JOIN handle h ON h.ROWID = m.handle_id
                WHERE cmj.chat_id = ?
                ORDER BY m.date ASC;
            """, (chat_rowid,))
            msgs = cur.fetchall()
            records = []
            for (msg_id, date_val, is_from_me, handle_id, text, body) in msgs:
                dt = apple_ns_to_unix(date_val)
                dt_str = dt.isoformat(sep=" ", timespec="seconds") if dt else ""
                direction = "Me" if is_from_me == 1 else (handle_id or "Other")
                records.append({"message_id": msg_id, "datetime_utc": dt_str, "from": direction, "text": message_text(text, body)})

            csv_path = base_dir / f"chat_with_{sanitize_filename(chat_name)}.csv"
            with csv_path.open("w", encoding="utf-8", newline="") as stream:
                writer = csv.DictWriter(stream, fieldnames=["message_id", "datetime_utc", "from", "text"])
                writer.writeheader()
                writer.writerows(records)
            log(f"Saved messages CSV: {csv_path}")

            if records:
                # Join by chat rather than binding every message ID: large chats
                # otherwise exceed SQLite's variable limit during export.
                cur.execute("""
                    SELECT maj.message_id, a.filename, a.transfer_name
                    FROM message_attachment_join maj
                    JOIN attachment a ON a.ROWID = maj.attachment_id
                    JOIN chat_message_join cmj ON cmj.message_id = maj.message_id
                    WHERE cmj.chat_id = ?;
                """, (chat_rowid,))
                atts = cur.fetchall()
                home = Path.home()
                attach_root = home / "Library" / "Messages" / "Attachments"
                copied = 0
                for (mid, filename, transfer_name) in atts:
                    src = None
                    if filename:
                        fpath = Path(filename).expanduser()
                        src = fpath if fpath.is_absolute() else attach_root / fpath
                    if (not src or not src.exists()) and transfer_name:
                        alt = attach_root / transfer_name
                        if alt.exists():
                            src = alt
                    if src and src.exists():
                        dest_name = sanitize_filename(f"{mid}_{src.name}", max_len=160)
                        dest_path = attachments_dir / dest_name
                        try:
                            shutil.copy2(src, dest_path)
                            copied += 1
                        except Exception as e:
                            log(f"Attachment copy error ({src}): {e}")
                    else:
                        log(f"Attachment unavailable locally · {transfer_name or filename or mid}")
                log(f"Saved {copied} attachment(s) to: {attachments_dir}")

        return csv_path

