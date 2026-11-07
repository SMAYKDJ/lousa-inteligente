"""Envia as setas do teclado para a apresentação em primeiro plano (Fase 6, RF19).

A lousa é um overlay que não rouba o foco (D017). Assim, a tecla vai para o
aplicativo da apresentação (navegador, PowerPoint, Keynote, Impress), que
avança ou volta o slide com → e ←.

Sem dependência nova (CLAUDE.md §4.4): ctypes com as bibliotecas do sistema.
- macOS: CGEventPost (ApplicationServices). O sistema só entrega o evento se o
  aplicativo que roda o Python (o Terminal) tiver permissão em
  Ajustes do Sistema → Privacidade e Segurança → Acessibilidade.
  Sem a permissão, o evento é descartado sem erro, por isso `ready()` consulta
  AXIsProcessTrusted antes.
- Windows: keybd_event (user32), seta como tecla estendida. Não validado (1.7).
- Outros: não envia, só registra.
"""

from __future__ import annotations

import ctypes
import logging
import sys

log = logging.getLogger(__name__)

NEXT, PREV = "next", "prev"

_MAC_KEYCODES = {NEXT: 124, PREV: 123}  # kVK_RightArrow, kVK_LeftArrow
_WIN_VK = {NEXT: 0x27, PREV: 0x25}  # VK_RIGHT, VK_LEFT
_KEYEVENTF_EXTENDEDKEY, _KEYEVENTF_KEYUP = 0x1, 0x2


class KeySender:
    """Interface: `send(direction)` devolve (enviou, motivo)."""

    name = "nenhum"

    def ready(self) -> tuple[bool, str]:
        return False, "sistema sem envio de teclas"

    def send(self, direction: str) -> tuple[bool, str]:
        return False, "sistema sem envio de teclas"


class MacKeySender(KeySender):
    name = "macos"

    def __init__(self) -> None:
        services = ctypes.CDLL("/System/Library/Frameworks/ApplicationServices.framework/ApplicationServices")
        foundation = ctypes.CDLL("/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation")
        self._create = services.CGEventCreateKeyboardEvent
        self._create.restype = ctypes.c_void_p
        self._create.argtypes = [ctypes.c_void_p, ctypes.c_uint16, ctypes.c_bool]
        self._post = services.CGEventPost
        self._post.restype = None
        self._post.argtypes = [ctypes.c_uint32, ctypes.c_void_p]
        self._trusted = services.AXIsProcessTrusted
        self._trusted.restype = ctypes.c_bool
        self._release = foundation.CFRelease
        self._release.argtypes = [ctypes.c_void_p]

    def ready(self) -> tuple[bool, str]:
        if self._trusted():
            return True, "ok"
        return False, ("sem permissão de Acessibilidade: libere o Terminal em Ajustes do Sistema → "
                       "Privacidade e Segurança → Acessibilidade e abra o programa de novo")

    def send(self, direction: str) -> tuple[bool, str]:
        ok, reason = self.ready()
        if not ok:
            return False, reason
        code = _MAC_KEYCODES[direction]
        for down in (True, False):
            event = self._create(None, code, down)
            if not event:
                return False, "CGEventCreateKeyboardEvent falhou"
            self._post(0, event)  # kCGHIDEventTap
            self._release(event)
        return True, "ok"


class WindowsKeySender(KeySender):
    name = "windows"

    def __init__(self) -> None:
        self._event = ctypes.windll.user32.keybd_event  # type: ignore[attr-defined]

    def ready(self) -> tuple[bool, str]:
        return True, "ok"

    def send(self, direction: str) -> tuple[bool, str]:
        vk = _WIN_VK[direction]
        self._event(vk, 0, _KEYEVENTF_EXTENDEDKEY, 0)
        self._event(vk, 0, _KEYEVENTF_EXTENDEDKEY | _KEYEVENTF_KEYUP, 0)
        return True, "ok"


def create_key_sender() -> KeySender:
    try:
        if sys.platform == "darwin":
            return MacKeySender()
        if sys.platform == "win32":
            return WindowsKeySender()
    except (OSError, AttributeError) as exc:
        log.warning("envio de teclas indisponível: %s", exc)
    return KeySender()
