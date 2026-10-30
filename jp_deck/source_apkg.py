"""Bounded, read-only reader for the supported modern APKG database format."""

from __future__ import annotations

import ctypes
import ctypes.util
import hashlib
import io
import sqlite3
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote
from typing import Any


class SourceError(ValueError):
    """A controlled source archive, database, or applicability rejection."""


MAX_ARCHIVE_BYTES = 256 * 1024 * 1024
MAX_DATABASE_BYTES = 64 * 1024 * 1024
DATABASE_MEMBER = "collection.anki21b"

NOTE_COLUMNS = ("id", "guid", "mid", "mod", "usn", "tags", "flds", "sfld", "csum", "flags", "data")
CARD_COLUMNS = (
    "id", "nid", "did", "ord", "mod", "usn", "type", "queue", "due", "ivl", "factor",
    "reps", "lapses", "left", "odue", "odid", "flags", "data",
)
REQUIRED_TABLES = {"col", "decks", "notetypes", "fields", "notes", "cards"}


@dataclass(frozen=True)
class SourceSnapshot:
    path: Path
    sha256: str
    database_member: str
    collection_version: int
    decks: dict[int, str]
    note_types: dict[int, tuple[str, tuple[str, ...]]]
    scoped_notes: tuple[dict[str, Any], ...]
    selected_notes: tuple[dict[str, Any], ...]
    selected_cards: dict[int, tuple[dict[str, Any], ...]]
    scoped_note_count: int
    all_note_count: int
    all_card_count: int


def file_sha256(path: Path) -> str:
    try:
        with Path(path).open("rb") as stream:
            return hashlib.file_digest(stream, "sha256").hexdigest()
    except OSError as exc:
        raise SourceError(f"Cannot read source file {path}: {exc}") from exc


def _zstd_decompress(frame: bytes) -> bytes:
    library_name = ctypes.util.find_library("zstd")
    if not library_name:
        raise SourceError("The system libzstd decoder is unavailable; cannot read collection.anki21b safely")
    try:
        library = ctypes.CDLL(library_name)
        library.ZSTD_getFrameContentSize.argtypes = [ctypes.c_void_p, ctypes.c_size_t]
        library.ZSTD_getFrameContentSize.restype = ctypes.c_ulonglong
        library.ZSTD_decompressBound.argtypes = [ctypes.c_void_p, ctypes.c_size_t]
        library.ZSTD_decompressBound.restype = ctypes.c_ulonglong
        library.ZSTD_decompress.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_size_t]
        library.ZSTD_decompress.restype = ctypes.c_size_t
        library.ZSTD_isError.argtypes = [ctypes.c_size_t]
        library.ZSTD_isError.restype = ctypes.c_uint
        library.ZSTD_getErrorName.argtypes = [ctypes.c_size_t]
        library.ZSTD_getErrorName.restype = ctypes.c_char_p
    except (AttributeError, OSError) as exc:
        raise SourceError(f"Cannot initialize libzstd safely: {exc}") from exc

    source = ctypes.create_string_buffer(frame)
    declared_size = int(library.ZSTD_getFrameContentSize(source, len(frame)))
    unknown_size = (1 << 64) - 1
    error_size = (1 << 64) - 2
    if declared_size == error_size:
        raise SourceError("collection.anki21b has an invalid Zstandard frame header")
    capacity = declared_size if declared_size != unknown_size else int(library.ZSTD_decompressBound(source, len(frame)))
    if capacity <= 0 or capacity > MAX_DATABASE_BYTES:
        raise SourceError(f"collection.anki21b decompressed size bound {capacity} exceeds the safe limit")
    destination = ctypes.create_string_buffer(capacity)
    result = int(library.ZSTD_decompress(destination, capacity, source, len(frame)))
    if library.ZSTD_isError(result):
        detail = library.ZSTD_getErrorName(result).decode("ascii", errors="replace")
        raise SourceError(f"Invalid Zstandard data in collection.anki21b: {detail}")
    if declared_size != unknown_size and result != declared_size:
        raise SourceError("collection.anki21b decompressed size disagrees with its frame header")
    return destination.raw[:result]


def _read_modern_database(path: Path, archive_bytes: bytes) -> bytes:
    try:
        with zipfile.ZipFile(io.BytesIO(archive_bytes), "r") as archive:
            members = [info for info in archive.infolist() if info.filename == DATABASE_MEMBER]
            if len(members) != 1:
                raise SourceError(
                    f"Source APKG must contain exactly one {DATABASE_MEMBER}; the legacy collection.anki2 stub is not a fallback"
                )
            info = members[0]
            if info.file_size <= 0 or info.file_size > MAX_DATABASE_BYTES:
                raise SourceError(f"{DATABASE_MEMBER} archive member exceeds the safe size limit")
            frame = archive.read(info)
    except (OSError, zipfile.BadZipFile, RuntimeError, EOFError) as exc:
        raise SourceError(f"Cannot safely read source APKG {path}: {exc}") from exc
    return _zstd_decompress(frame)


def _dict_rows(cursor: sqlite3.Cursor) -> list[dict[str, Any]]:
    names = [column[0] for column in cursor.description or ()]
    return [dict(zip(names, row, strict=True)) for row in cursor.fetchall()]


def read_source_snapshot(
    path: Path,
    *,
    expected_sha256: str,
    deck_ids: tuple[int, ...],
    note_type_ids: tuple[int, ...],
    selection_count: int,
    selection_native_ids: tuple[int, ...] | None = None,
) -> SourceSnapshot:
    """Verify the declared fingerprint/layout and freeze selection before eligibility checks."""
    path = Path(path).resolve()
    if not path.is_file():
        raise SourceError(f"Source APKG does not exist: {path}")
    if path.stat().st_size > MAX_ARCHIVE_BYTES:
        raise SourceError(f"Source APKG exceeds the safe {MAX_ARCHIVE_BYTES}-byte archive limit: {path}")
    try:
        archive_bytes = path.read_bytes()
    except OSError as exc:
        raise SourceError(f"Cannot read source APKG {path}: {exc}") from exc
    if len(archive_bytes) > MAX_ARCHIVE_BYTES:
        raise SourceError(f"Source APKG exceeds the safe {MAX_ARCHIVE_BYTES}-byte archive limit: {path}")
    actual_hash = hashlib.sha256(archive_bytes).hexdigest()
    if actual_hash != expected_sha256.lower():
        raise SourceError(f"Source APKG SHA-256 mismatch: expected {expected_sha256}, got {actual_hash}")
    database = _read_modern_database(path, archive_bytes)

    with tempfile.TemporaryDirectory(prefix="jp-deck-source-") as temp_dir:
        database_path = Path(temp_dir) / "collection.anki21b.sqlite"
        database_path.write_bytes(database)
        database_path.chmod(0o400)
        uri = f"file:{quote(str(database_path), safe='/')}?mode=ro&immutable=1"
        try:
            connection = sqlite3.connect(uri, uri=True)
            connection.create_collation(
                "unicase",
                lambda left, right: (left.casefold() > right.casefold()) - (left.casefold() < right.casefold()),
            )
            connection.row_factory = None
            connection.execute("PRAGMA query_only=ON")
            integrity = connection.execute("PRAGMA integrity_check").fetchone()
            if not integrity or integrity[0] != "ok":
                raise SourceError(f"Main collection database failed integrity_check: {integrity!r}")
            tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            missing_tables = sorted(REQUIRED_TABLES - tables)
            if missing_tables:
                raise SourceError(f"Unsupported main collection layout; missing table(s): {', '.join(missing_tables)}")
            col_columns = {row[1] for row in connection.execute("PRAGMA table_info(col)")}
            if "ver" not in col_columns:
                raise SourceError("Unsupported main collection layout: col.ver is missing")
            version_rows = connection.execute("SELECT ver FROM col").fetchall()
            if len(version_rows) != 1 or version_rows[0][0] != 18:
                raise SourceError(f"Unsupported main collection schema version: {version_rows!r}; expected version 18")
            for table, required in (("notes", NOTE_COLUMNS), ("cards", CARD_COLUMNS)):
                actual_columns = {row[1] for row in connection.execute(f"PRAGMA table_info({table})")}
                missing = sorted(set(required) - actual_columns)
                if missing:
                    raise SourceError(f"Unsupported main collection layout: {table} missing {', '.join(missing)}")

            deck_rows = connection.execute("SELECT id, name FROM decks").fetchall()
            decks = {int(row[0]): str(row[1]) for row in deck_rows}
            missing_decks = [deck_id for deck_id in deck_ids if deck_id not in decks]
            if missing_decks:
                raise SourceError(f"Configured source deck ID(s) are absent from the main collection: {missing_decks}")

            type_rows = connection.execute("SELECT id, name FROM notetypes").fetchall()
            note_types: dict[int, tuple[str, tuple[str, ...]]] = {}
            for model_id, name in type_rows:
                field_rows = connection.execute(
                    "SELECT name FROM fields WHERE ntid=? ORDER BY ord ASC", (model_id,)
                ).fetchall()
                note_types[int(model_id)] = (str(name), tuple(str(row[0]) for row in field_rows))
            for model_id in note_type_ids:
                if model_id not in note_types:
                    raise SourceError(f"Configured supported note type ID {model_id} is absent from the main collection")

            note_sql = (
                "SELECT n.id, n.guid, n.mid, n.mod, n.usn, n.tags, n.flds, n.sfld, n.csum, n.flags, n.data "
                "FROM notes AS n WHERE EXISTS (SELECT 1 FROM cards AS c WHERE c.nid=n.id "
                f"AND c.did IN ({','.join('?' for _ in deck_ids)})) ORDER BY n.id ASC"
            )
            scoped_notes = _dict_rows(connection.execute(note_sql, deck_ids))
            if selection_native_ids is None:
                if len(scoped_notes) < selection_count:
                    raise SourceError(
                        f"Source deck scope has {len(scoped_notes)} notes; cannot freeze the requested first {selection_count}"
                    )
                selected_notes = scoped_notes[:selection_count]
            else:
                if selection_count != len(selection_native_ids) or selection_count <= 0:
                    raise SourceError("Explicit source selection count must equal its nonempty ordered native-ID list")
                if len(set(selection_native_ids)) != len(selection_native_ids):
                    raise SourceError("Explicit source selection contains duplicate native note IDs")
                scoped_by_id = {int(note["id"]): note for note in scoped_notes}
                unknown = [native_id for native_id in selection_native_ids if native_id not in scoped_by_id]
                if unknown:
                    raise SourceError(f"Explicit source selection includes unknown/out-of-scope native note ID(s): {unknown}")
                if tuple(sorted(selection_native_ids)) != selection_native_ids:
                    raise SourceError("Explicit source selection native IDs must be in ascending canonical order")
                selected_notes = [scoped_by_id[native_id] for native_id in selection_native_ids]
            all_note_count = int(connection.execute("SELECT COUNT(*) FROM notes").fetchone()[0])
            all_card_count = int(connection.execute("SELECT COUNT(*) FROM cards").fetchone()[0])
            selected_cards: dict[int, tuple[dict[str, Any], ...]] = {}
            card_sql = "SELECT " + ", ".join(CARD_COLUMNS) + " FROM cards WHERE nid=? ORDER BY id ASC"
            for note in selected_notes:
                note_id = int(note["id"])
                selected_cards[note_id] = tuple(_dict_rows(connection.execute(card_sql, (note_id,))))
                if not selected_cards[note_id]:
                    raise SourceError(f"Selected native note {note_id} has no card relation")
                if not any(int(card["did"]) in deck_ids for card in selected_cards[note_id]):
                    raise SourceError(f"Selected native note {note_id} has no card in the configured source deck")
        except sqlite3.Error as exc:
            raise SourceError(f"Cannot read supported main collection database safely: {exc}") from exc
        finally:
            try:
                connection.close()
            except (UnboundLocalError, sqlite3.Error):
                pass

    return SourceSnapshot(
        path=path,
        sha256=actual_hash,
        database_member=DATABASE_MEMBER,
        collection_version=18,
        decks=decks,
        note_types=note_types,
        scoped_notes=tuple(scoped_notes),
        selected_notes=tuple(selected_notes),
        selected_cards=selected_cards,
        scoped_note_count=len(scoped_notes),
        all_note_count=all_note_count,
        all_card_count=all_card_count,
    )
