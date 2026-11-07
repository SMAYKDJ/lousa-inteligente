"""Painel de cor/espessura/borracha (RF20, RF21): modelo e janela."""

import os

import pytest

from desktop import config
from desktop.drawing.board import Board
from desktop.drawing.style import DrawingStyle
from desktop.drawing.tools import ToolController
from desktop.interface.sidebar_model import Edge, SidebarModel, SidebarState, Tool
from desktop.interface.style_panel import StylePanel, is_style_key


def expanded(edge=Edge.LEFT, tool=Tool.BRUSH):
    sb = SidebarModel(1920, 1080, edge=edge)
    sb.state, sb.tool = SidebarState.EXPANDED, tool
    return sb


def test_style_defaults_and_apply():
    st = DrawingStyle()
    assert st.color == config.BRUSH_COLORS[0][1] and st.width_frac == config.BRUSH_WIDTHS_FRAC[1]
    assert st.apply("color", 1) == {"event": "ui_style", "color": "Azul"}
    assert st.color == "#1e6fd9"
    st.apply("width", 2); st.apply("eraser", 0)
    assert st.width_frac == config.BRUSH_WIDTHS_FRAC[2] and st.eraser_frac == config.ERASER_RADII_FRAC[0]


def test_brush_panel_has_colors_and_widths_beside_sidebar():
    sb, sp = expanded(), StylePanel()
    sp.on_tool(Tool.BRUSH)
    lay = sp.layout(sb, 0.0)
    keys = [k for k, _ in lay.buttons]
    assert keys == [("color", i) for i in range(5)] + [("width", i) for i in range(3)]
    bar = sb.layout(0.0).panel
    assert lay.panel.x >= bar.x + bar.w  # à direita da sidebar (borda esquerda)
    for _, r in lay.buttons:
        assert lay.panel.contains(*r.center)


def test_eraser_panel_and_hidden_cases():
    sb, sp = expanded(tool=Tool.ERASER), StylePanel()
    sp.on_tool(Tool.ERASER)
    assert [k for k, _ in sp.layout(sb, 0.0).buttons] == [("eraser", i) for i in range(3)]
    sp.on_tool(Tool.CIRCLE)
    assert sp.layout(sb, 0.0) is None
    sp.on_tool(Tool.ERASER); sb.state = SidebarState.COLLAPSED
    assert sp.layout(sb, 0.0) is None and sp.targets(sb, 0.0) == []


@pytest.mark.parametrize("edge", list(Edge))
def test_panel_inside_screen_and_off_sidebar_for_every_edge(edge):
    sb, sp = expanded(edge), StylePanel()
    sp.on_tool(Tool.BRUSH)
    p, bar = sp.layout(sb, 0.0).panel, sb.layout(0.0).panel
    assert 0 <= p.x and p.x + p.w <= 1920 and 0 <= p.y and p.y + p.h <= 1080
    overlap = p.x < bar.x + bar.w and bar.x < p.x + p.w and p.y < bar.y + bar.h and bar.y < p.y + p.h
    assert not overlap


def test_tools_use_style_and_strokes_keep_their_color():
    b, st = Board(), DrawingStyle()
    c = ToolController(b, st)
    st.apply("color", 1); st.apply("width", 2)
    for i in range(10):
        c.update(Tool.BRUSH, True, (0.1 + 0.02 * i, 0.5), False, (1000, 500), i * 0.03)
    c.update(Tool.BRUSH, False, None, False, (1000, 500), 1.0)
    st.apply("color", 4)
    assert b.items[0].color == "#1e6fd9" and b.items[0].width == config.BRUSH_WIDTHS_FRAC[2]


def test_is_style_key():
    assert is_style_key(("color", 0)) and not is_style_key(Tool.BRUSH) and not is_style_key(("x", 1))
