"""Ajustes de sistema para a lousa ficar por cima da apresentação (Fase 3, etapa 3.0).

O Qt oferece "sempre por cima", "sem moldura" e "transparente para o mouse".
No macOS isso não basta para aparecer sobre uma apresentação em TELA CHEIA:
o navegador, o PowerPoint e o Keynote abrem um Space próprio.

1º teste real (2026-11-06 20:18): a lousa aparecia sobre a área de trabalho
comum, mas sumia quando o navegador entrava em tela cheia. Receita usada
por overlays no macOS:
- janela do tipo painel (Qt.Tool → NSPanel) que NÃO se esconde quando outro
  aplicativo fica ativo (`setHidesOnDeactivate: NO`) e que não rouba o foco
  (`NSWindowStyleMaskNonactivatingPanel`);
- presente em todos os Spaces e como auxiliar de tela cheia (collectionBehavior);
- nível de janela alto;
- aplicativo como "acessório" (sem ícone no Dock): só assim as janelas dele
  entram no Space de tela cheia de OUTRO aplicativo.

Usa o runtime do Objective-C por `ctypes` (vem com o Python), sem dependência
nova (CLAUDE.md §4.4). Em outros sistemas não faz nada: o Windows é validado
na etapa 1.7.
"""

from __future__ import annotations

import logging
import sys

log = logging.getLogger(__name__)

# NSWindowCollectionBehavior (AppKit).
_CAN_JOIN_ALL_SPACES = 1 << 0
_STATIONARY = 1 << 4
_FULL_SCREEN_AUXILIARY = 1 << 8
# NSWindowStyleMask.
_NONACTIVATING_PANEL = 1 << 7
# NSApplicationActivationPolicy.
_ACCESSORY = 1

#: Nível da janela. 1000 = NSScreenSaverWindowLevel: acima de apresentações em
#: tela cheia e da barra de menus.
MAC_WINDOW_LEVEL = 1000


class _ObjC:
    """Chamadas mínimas ao runtime Objective-C, com o tipo certo para cada uma (arm64)."""

    def __init__(self) -> None:
        import ctypes
        import ctypes.util

        c = ctypes
        lib = c.cdll.LoadLibrary(c.util.find_library("objc"))
        lib.sel_registerName.restype = c.c_void_p
        lib.sel_registerName.argtypes = [c.c_char_p]
        lib.objc_getClass.restype = c.c_void_p
        lib.objc_getClass.argtypes = [c.c_char_p]
        self.lib = lib

        def fn(restype, *argtypes):
            return c.CFUNCTYPE(restype, c.c_void_p, c.c_void_p, *argtypes)(("objc_msgSend", lib))

        self.ptr = fn(c.c_void_p)
        self.ulong = fn(c.c_ulong)
        self.bool_ = fn(c.c_bool, c.c_void_p)
        self.set_ulong = fn(None, c.c_ulong)
        self.set_long = fn(None, c.c_long)
        self.set_bool = fn(None, c.c_bool)
        self.void = fn(None)

    def sel(self, name: str):
        return self.lib.sel_registerName(name.encode())

    def responds(self, obj, name: str) -> bool:
        return bool(self.bool_(obj, self.sel("respondsToSelector:"), self.sel(name)))


_objc: _ObjC | None = None


def _runtime() -> _ObjC:
    global _objc
    if _objc is None:
        _objc = _ObjC()
    return _objc


def make_overlay_window(widget) -> bool:
    """Aplica os ajustes do sistema. Devolve True se aplicou, False se não precisou ou falhou."""
    if sys.platform != "darwin":
        return False
    try:
        return _mac_overlay(int(widget.winId()))
    except Exception:  # noqa: BLE001 — sem o ajuste a lousa ainda funciona fora da tela cheia
        log.exception("Não foi possível ajustar a janela da lousa para tela cheia no macOS")
        return False


def keep_on_top(widget) -> None:
    """Reafirma a janela na frente (chamado periodicamente no macOS)."""
    if sys.platform != "darwin":
        return
    try:
        objc = _runtime()
        window = objc.ptr(int(widget.winId()), objc.sel("window"))
        if window:
            objc.void(window, objc.sel("orderFrontRegardless"))
    except Exception:  # noqa: BLE001
        log.debug("orderFrontRegardless falhou", exc_info=True)


def _mac_overlay(view_pointer: int) -> bool:
    objc = _runtime()
    app = objc.ptr(objc.lib.objc_getClass(b"NSApplication"), objc.sel("sharedApplication"))
    if app:
        objc.set_long(app, objc.sel("setActivationPolicy:"), _ACCESSORY)

    window = objc.ptr(view_pointer, objc.sel("window"))
    if not window:
        return False
    if objc.responds(window, "setHidesOnDeactivate:"):
        objc.set_bool(window, objc.sel("setHidesOnDeactivate:"), False)
    if objc.responds(window, "styleMask"):
        mask = objc.ulong(window, objc.sel("styleMask"))
        objc.set_ulong(window, objc.sel("setStyleMask:"), mask | _NONACTIVATING_PANEL)
    behavior = _CAN_JOIN_ALL_SPACES | _STATIONARY | _FULL_SCREEN_AUXILIARY
    objc.set_ulong(window, objc.sel("setCollectionBehavior:"), behavior)
    objc.set_long(window, objc.sel("setLevel:"), MAC_WINDOW_LEVEL)
    objc.void(window, objc.sel("orderFrontRegardless"))
    log.info("Lousa ajustada para ficar sobre apresentações em tela cheia (macOS)")
    return True
