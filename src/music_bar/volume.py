"""Volume slider menu items laid out like the macOS Control Center volume control."""

from collections.abc import Callable

import rumps
from AppKit import (
    NSColor,
    NSFont,
    NSImage,
    NSImageView,
    NSMakeRect,
    NSTextAlignmentRight,
    NSTextField,
    NSView,
    NSViewMinXMargin,
    NSViewWidthSizable,
)

# Horizontal inset matching standard menu item text padding.
INSET = 14
ICON_SIZE = 16
ICON_GAP = 8
ROW_HEIGHT = 26
INITIAL_WIDTH = 240  # Views are width-sizable, so the menu stretches them to its own width.


def _label(text: str, frame: tuple[float, float, float, float]) -> NSTextField:
    field = NSTextField.labelWithString_(text)
    field.setFrame_(NSMakeRect(*frame))
    field.setFont_(NSFont.menuFontOfSize_(0))
    field.setTextColor_(NSColor.secondaryLabelColor())
    return field


class VolumeHeaderMenuItem(rumps.MenuItem):
    """A header row with a title on the left and the current percentage on the right."""

    def __init__(self, title: str, value: float = 0) -> None:
        super().__init__(title)
        label_height = 17
        y = (ROW_HEIGHT - label_height) / 2
        view = NSView.alloc().initWithFrame_(NSMakeRect(0, 0, INITIAL_WIDTH, ROW_HEIGHT))
        view.setAutoresizingMask_(NSViewWidthSizable)

        title_field = _label(title, (INSET, y, INITIAL_WIDTH - INSET * 2 - 50, label_height))
        view.addSubview_(title_field)

        self._percent = _label("", (INITIAL_WIDTH - INSET - 50, y, 50, label_height))
        self._percent.setAlignment_(NSTextAlignmentRight)
        self._percent.setAutoresizingMask_(NSViewMinXMargin)
        view.addSubview_(self._percent)

        self._menuitem.setView_(view)
        self.set_percent(value)

    def set_percent(self, value: float) -> None:
        self._percent.setStringValue_(f"{round(value)}%")


class VolumeSliderMenuItem(rumps.SliderMenuItem):
    """A full-width slider with a leading speaker icon and menu-aligned padding."""

    def __init__(
        self,
        value: float = 50,
        callback: Callable[["VolumeSliderMenuItem"], None] | None = None,
        header: VolumeHeaderMenuItem | None = None,
    ) -> None:
        self._header = header
        self._user_callback = callback
        super().__init__(value=value, callback=self._on_change, dimensions=(INITIAL_WIDTH, ROW_HEIGHT))

        # rumps installed the bare slider as the item's view; detach it before re-parenting.
        self._menuitem.setView_(None)

        view = NSView.alloc().initWithFrame_(NSMakeRect(0, 0, INITIAL_WIDTH, ROW_HEIGHT))
        view.setAutoresizingMask_(NSViewWidthSizable)

        slider_x = INSET
        icon = NSImage.imageWithSystemSymbolName_accessibilityDescription_("speaker.wave.2.fill", "Volume")
        if icon is not None:
            icon.setTemplate_(True)
            icon_view = NSImageView.imageViewWithImage_(icon)
            icon_view.setFrame_(NSMakeRect(INSET, (ROW_HEIGHT - ICON_SIZE) / 2, ICON_SIZE, ICON_SIZE))
            icon_view.setContentTintColor_(NSColor.secondaryLabelColor())
            view.addSubview_(icon_view)
            slider_x += ICON_SIZE + ICON_GAP

        self._slider.setFrame_(NSMakeRect(slider_x, 0, INITIAL_WIDTH - slider_x - INSET, ROW_HEIGHT))
        self._slider.setAutoresizingMask_(NSViewWidthSizable)
        self._slider.setContinuous_(True)
        view.addSubview_(self._slider)
        self._menuitem.setView_(view)

    def _on_change(self, sender: "VolumeSliderMenuItem") -> None:
        if self._header is not None:
            self._header.set_percent(sender.value)
        if self._user_callback is not None:
            self._user_callback(sender)

    @property
    def value(self) -> float:
        return self._slider.doubleValue()

    @value.setter
    def value(self, new_value: float) -> None:
        self._slider.setDoubleValue_(new_value)
        if self._header is not None:
            self._header.set_percent(new_value)
