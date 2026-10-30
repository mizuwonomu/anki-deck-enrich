"""Fabricated APKG writer used to exercise the production Tango mapping code."""

from __future__ import annotations

import ctypes
import ctypes.util
import sqlite3
import tempfile
import zipfile
from pathlib import Path
from typing import Any

from jp_deck.source_apkg import CARD_COLUMNS, DATABASE_MEMBER
from jp_deck.sources.tango_n1_mimi.adapter import FIELD_SIGNATURE

SYNTHETIC_DECK_ID = 70001
SYNTHETIC_NOTE_TYPE_ID = 70002
SYNTHETIC_FIELDS = FIELD_SIGNATURE


def write_synthetic_apkg(
    path: Path,
    notes: list[dict[str, Any]],
    *,
    version: int = 18,
    signature: tuple[str, ...] = SYNTHETIC_FIELDS,
    malformed_frame: bool = False,
    only_legacy_stub: bool = False,
) -> None:
    """Write a tiny, original modern APKG with synthetic notes/cards and no real payload."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if only_legacy_stub:
        with zipfile.ZipFile(path, "w") as archive:
            archive.writestr("collection.anki2", b"synthetic legacy-only warning stub")
        return
    with tempfile.TemporaryDirectory(prefix="jp-deck-synthetic-source-") as directory:
        database_path = Path(directory) / "collection.sqlite"
        connection = sqlite3.connect(database_path)
        try:
            connection.executescript(
                "CREATE TABLE col(ver INTEGER NOT NULL);"
                "CREATE TABLE decks(id INTEGER PRIMARY KEY, name TEXT NOT NULL);"
                "CREATE TABLE notetypes(id INTEGER PRIMARY KEY, name TEXT NOT NULL);"
                "CREATE TABLE fields(ntid INTEGER NOT NULL, ord INTEGER NOT NULL, name TEXT NOT NULL, PRIMARY KEY(ntid,ord));"
                "CREATE TABLE notes(id INTEGER PRIMARY KEY, guid TEXT NOT NULL, mid INTEGER NOT NULL, mod INTEGER NOT NULL, usn INTEGER NOT NULL, tags TEXT NOT NULL, flds TEXT NOT NULL, sfld, csum INTEGER NOT NULL, flags INTEGER NOT NULL, data TEXT NOT NULL);"
                "CREATE TABLE cards(id INTEGER PRIMARY KEY, nid INTEGER NOT NULL, did INTEGER NOT NULL, ord INTEGER NOT NULL, mod INTEGER NOT NULL, usn INTEGER NOT NULL, type INTEGER NOT NULL, queue INTEGER NOT NULL, due INTEGER NOT NULL, ivl INTEGER NOT NULL, factor INTEGER NOT NULL, reps INTEGER NOT NULL, lapses INTEGER NOT NULL, left INTEGER NOT NULL, odue INTEGER NOT NULL, odid INTEGER NOT NULL, flags INTEGER NOT NULL, data TEXT NOT NULL);"
            )
            connection.execute("INSERT INTO col VALUES (?)", (version,))
            connection.execute("INSERT INTO decks VALUES (?, ?)", (SYNTHETIC_DECK_ID, "Fabricated test deck"))
            connection.execute("INSERT INTO notetypes VALUES (?, ?)", (SYNTHETIC_NOTE_TYPE_ID, "Fabricated test note type"))
            connection.executemany("INSERT INTO fields VALUES (?, ?, ?)",
                                   [(SYNTHETIC_NOTE_TYPE_ID, index, field) for index, field in enumerate(signature)])
            for note in notes:
                native_id = int(note["id"])
                field_values = [str(note.get(field, "")) for field in signature]
                connection.execute(
                    "INSERT INTO notes VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                    (native_id, f"synthetic-guid-{native_id}", SYNTHETIC_NOTE_TYPE_ID, 1, 0, "",
                     "\x1f".join(field_values), field_values[0] if field_values else "", native_id % 65536, 0, ""),
                )
                card_specs = note.get("cards")
                if card_specs is None:
                    card_specs = [{} for _ in range(int(note.get("card_count", 1)))]
                for ordinal, card_spec in enumerate(card_specs):
                    connection.execute(
                        "INSERT INTO cards VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                        (native_id * 100 + ordinal + 1, native_id, int(card_spec.get("did", SYNTHETIC_DECK_ID)),
                         int(card_spec.get("ord", ordinal)), 1, 0, int(card_spec.get("type", 0)),
                         int(card_spec.get("queue", 0)), int(card_spec.get("due", ordinal + 1)),
                         0, 0, 0, 0, 1, 0, 0, 0, "{}"),
                    )
            connection.commit()
        finally:
            connection.close()
        if malformed_frame:
            frame = b"not a valid synthetic zstandard frame"
        else:
            library_name = ctypes.util.find_library("zstd")
            if not library_name:
                raise RuntimeError("system libzstd is required by the APKG reader test")
            library = ctypes.CDLL(library_name)
            library.ZSTD_compressBound.argtypes = [ctypes.c_size_t]
            library.ZSTD_compressBound.restype = ctypes.c_size_t
            library.ZSTD_compress.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_int]
            library.ZSTD_compress.restype = ctypes.c_size_t
            raw_database = database_path.read_bytes()
            source_buffer = ctypes.create_string_buffer(raw_database)
            capacity = int(library.ZSTD_compressBound(len(raw_database)))
            destination = ctypes.create_string_buffer(capacity)
            size = int(library.ZSTD_compress(destination, capacity, source_buffer, len(raw_database), 3))
            frame = destination.raw[:size]
        with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_STORED) as archive:
            archive.writestr(DATABASE_MEMBER, frame)
            archive.writestr("collection.anki2", b"synthetic ignored legacy stub")
