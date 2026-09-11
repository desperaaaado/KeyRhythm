from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import Qt


@dataclass(frozen=True, slots=True)
class KeyBinding:
    qt_key: Qt.Key
    label: str


KEY_LAYOUTS: dict[int, tuple[KeyBinding, ...]] = {
    4: tuple(KeyBinding(key, label) for key, label in zip(
        (Qt.Key.Key_D, Qt.Key.Key_F, Qt.Key.Key_J, Qt.Key.Key_K), "DFJK"
    )),
    6: tuple(KeyBinding(key, label) for key, label in zip(
        (Qt.Key.Key_S, Qt.Key.Key_D, Qt.Key.Key_F, Qt.Key.Key_J, Qt.Key.Key_K, Qt.Key.Key_L), "SDFJKL"
    )),
    8: tuple(KeyBinding(key, label) for key, label in zip(
        (Qt.Key.Key_A, Qt.Key.Key_S, Qt.Key.Key_D, Qt.Key.Key_F,
         Qt.Key.Key_J, Qt.Key.Key_K, Qt.Key.Key_L, Qt.Key.Key_Semicolon),
        ("A", "S", "D", "F", "J", "K", "L", ";"),
    )),
    17: tuple(KeyBinding(key, label) for key, label in zip(
        (Qt.Key.Key_A, Qt.Key.Key_W, Qt.Key.Key_S, Qt.Key.Key_E, Qt.Key.Key_D,
         Qt.Key.Key_F, Qt.Key.Key_T, Qt.Key.Key_G, Qt.Key.Key_Y, Qt.Key.Key_H,
         Qt.Key.Key_U, Qt.Key.Key_J, Qt.Key.Key_K, Qt.Key.Key_O, Qt.Key.Key_L,
         Qt.Key.Key_P, Qt.Key.Key_Semicolon),
        ("A", "W", "S", "E", "D", "F", "T", "G", "Y", "H", "U", "J", "K", "O", "L", "P", ";"),
    )),
}


def bindings_for(key_count: int) -> tuple[KeyBinding, ...]:
    try:
        return KEY_LAYOUTS[key_count]
    except KeyError as error:
        raise ValueError(f"unsupported key count: {key_count}") from error


def key_index_for(key_count: int, qt_key: int) -> int | None:
    for index, binding in enumerate(bindings_for(key_count)):
        if int(binding.qt_key) == int(qt_key):
            return index
    return None


def midi_note_name(pitch: int) -> str:
    names = ("C", "C♯", "D", "D♯", "E", "F", "F♯", "G", "G♯", "A", "A♯", "B")
    return f"{names[pitch % 12]}{pitch // 12 - 1}"
