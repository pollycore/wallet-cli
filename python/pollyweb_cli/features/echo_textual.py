"""Interactive Textual viewer for `pw echo --debug`."""

from __future__ import annotations

from collections.abc import Callable
import sys
from dataclasses import dataclass

try:
    from textual.app import App, ComposeResult
    from textual.containers import Horizontal, Vertical, VerticalScroll
    from textual.widgets import Link, Static
except ImportError:  # pragma: no cover - dependency is expected in runtime envs
    App = None
    ComposeResult = object
    Horizontal = None
    Vertical = None
    VerticalScroll = None
    Link = None
    Static = None

from pollyweb_cli.features.echo_rendering import _render_section_title


TEXTUAL_AVAILABLE = App is not None


@dataclass(frozen = True)
class _EchoTextualSection:
    """One section shown in the interactive Textual echo viewer."""

    title: str
    body: object
    copy_text: str | None = None


SectionBuilder = Callable[[], list[_EchoTextualSection]]


class _EchoTextualApp(App[None] if TEXTUAL_AVAILABLE else object):
    """TTY-only Textual viewer for the interactive echo result layout."""

    CSS = """
    Screen {
        layout: vertical;
    }

    #body {
        height: 1fr;
    }

    #header-bar {
        height: auto;
        margin: 0 0 1 0;
    }

    #header-panel {
        width: 1fr;
    }

    #header-controls {
        width: auto;
        height: auto;
        align: right middle;
        border: round #d7875f;
        border-title-align: left;
        border-title-color: #d7875f;
        border-title-style: bold;
        padding: 0 0;
    }

    .section-bar {
        height: auto;
        margin: 0 0 0 0;
    }

    .section-title {
        width: 1fr;
    }

    .section-controls {
        width: auto;
        height: auto;
        align: right middle;
    }

    .section-block {
        height: auto;
        margin: 0 0 1 0;
    }

    .section-content {
        height: auto;
    }

    .code-content {
        width: 1fr;
        background: #262620;
    }

    .control-link {
        width: auto;
        min-width: 0;
        min-height: 1;
        margin: 0 0 0 0;
        padding: 0 1 0 0;
        color: #3b82f6;
    }

    .copy-link {
        width: auto;
        min-width: 0;
        min-height: 1;
        margin: 0 0 0 1;
        padding: 0 0;
        color: #3b82f6;
    }

    .is-active {
        color: #d7875f;
        text-style: bold underline;
    }
    """
    BINDINGS = [
        ("q", "quit", "Quit"),
        ("x", "quit", "Quit"),
        ("escape", "quit", "Quit"),
        ("ctrl+c", "quit", "Quit"),
        ("ctrl+w", "quit", "Quit"),
        ("up", "scroll_up", "Up"),
        ("down", "scroll_down", "Down"),
        ("pageup", "scroll_page_up", "Page up"),
        ("pagedown", "scroll_page_down", "Page down"),
        ("y", "show_yaml", "YAML"),
        ("j", "show_json", "JSON"),
        ("r", "show_raw", "Raw"),
    ]

    def __init__(
        self,
        *,
        header_panel,
        yaml_sections: list[_EchoTextualSection] | SectionBuilder,
        json_sections: list[_EchoTextualSection] | SectionBuilder,
        raw_sections: list[_EchoTextualSection] | SectionBuilder,
        footer_panel,
        initial_payload_format: str
    ) -> None:
        """Store the renderables needed by the echo viewer."""

        super().__init__()
        self._header_panel = header_panel
        self._yaml_sections = yaml_sections
        self._json_sections = json_sections
        self._raw_sections = raw_sections
        self._footer_panel = footer_panel
        self._payload_format = initial_payload_format
        self._copied_section: tuple[str, int] | None = None
        self._copied_reset_timer = None
        self._section_cache: dict[str, list[_EchoTextualSection]] = {}
        self._exit_code = 0

    def _resolve_sections(
        self,
        payload_format: str
    ) -> list[_EchoTextualSection]:
        """Build and cache section lists only when a view is first opened."""

        cached_sections = self._section_cache.get(payload_format)
        if cached_sections is not None:
            return cached_sections

        section_source: list[_EchoTextualSection] | SectionBuilder
        if payload_format == "json":
            section_source = self._json_sections
        elif payload_format == "raw":
            section_source = self._raw_sections
        else:
            section_source = self._yaml_sections

        resolved_sections = (
            section_source()
            if callable(section_source)
            else section_source
        )
        self._section_cache[payload_format] = resolved_sections
        return resolved_sections

    def _current_sections(self) -> list[_EchoTextualSection]:
        """Return the current section list for the selected payload format."""

        return self._resolve_sections(self._payload_format)

    def _body_scroll(self, method_name: str) -> None:
        """Forward a keyboard scroll action to the main scrollable body."""

        scroll_view = self.query_one("#body")
        getattr(scroll_view, method_name)(animate = False)

    def action_show_yaml(self) -> None:
        """Switch the interactive payload view to YAML."""

        self._payload_format = "yaml"
        self._clear_copied_feedback()
        self.refresh(recompose = True)

    def action_show_json(self) -> None:
        """Switch the interactive payload view to JSON."""

        self._payload_format = "json"
        self._clear_copied_feedback()
        self.refresh(recompose = True)

    def action_show_raw(self) -> None:
        """Switch the interactive payload view to raw JSON."""

        self._payload_format = "raw"
        self._clear_copied_feedback()
        self.refresh(recompose = True)

    def action_scroll_up(self) -> None:
        """Scroll the interactive body upward by one line."""

        self._body_scroll("scroll_up")

    def action_scroll_down(self) -> None:
        """Scroll the interactive body downward by one line."""

        self._body_scroll("scroll_down")

    def action_scroll_page_up(self) -> None:
        """Scroll the interactive body upward by one page."""

        self._body_scroll("scroll_page_up")

    def action_scroll_page_down(self) -> None:
        """Scroll the interactive body downward by one page."""

        self._body_scroll("scroll_page_down")

    def _clear_copied_feedback(self) -> None:
        """Clear any active copy feedback and stop its pending reset timer."""

        self._copied_section = None
        if self._copied_reset_timer is not None:
            self._copied_reset_timer.stop()
            self._copied_reset_timer = None

    def _reset_copied_feedback(
        self,
        copied_section: tuple[str, int]
    ) -> None:
        """Restore the copy link label after the transient copied state."""

        self._copied_reset_timer = None
        if self._copied_section == copied_section:
            self._copied_section = None
            self.refresh(recompose = True)

    def open_url(
        self,
        url: str,
        *,
        new_tab: bool = True
    ) -> None:
        """Route internal link actions without leaving the Textual app."""

        if url == "action://show-yaml":
            self.action_show_yaml()
            return

        if url == "action://show-json":
            self.action_show_json()
            return

        if url == "action://show-raw":
            self.action_show_raw()
            return

        if url.startswith("action://copy/"):
            copy_index = int(url.removeprefix("action://copy/"))
            section = self._current_sections()[copy_index]
            if section.copy_text is not None:
                self.copy_to_clipboard(section.copy_text)
                copied_section = (self._payload_format, copy_index)
                self._clear_copied_feedback()
                self._copied_section = copied_section
                self._copied_reset_timer = self.set_timer(
                    1.0,
                    lambda: self._reset_copied_feedback(copied_section),
                )
                self.refresh(recompose = True)
            return

        super().open_url(url, new_tab = new_tab)

    def compose(self) -> ComposeResult:
        """Compose the reactive echo layout."""

        header_controls = Vertical(
            Link(
                "Yaml",
                url = "action://show-yaml",
                id = "toggle-yaml",
                classes = (
                    "control-link is-active"
                    if self._payload_format == "yaml"
                    else "control-link"
                ),
            ),
            Link(
                "Json",
                url = "action://show-json",
                id = "toggle-json",
                classes = (
                    "control-link is-active"
                    if self._payload_format == "json"
                    else "control-link"
                ),
            ),
            Link(
                "Raw",
                url = "action://show-raw",
                id = "toggle-raw",
                classes = (
                    "control-link is-active"
                    if self._payload_format == "raw"
                    else "control-link"
                ),
            ),
            id = "header-controls",
        )
        yield Horizontal(
            Static(self._header_panel, id = "header-panel"),
            header_controls,
            id = "header-bar",
        )
        yield VerticalScroll(
            *[
                Vertical(
                    Horizontal(
                        Static(
                            _render_section_title(section.title),
                            classes = "section-title",
                        ),
                        Horizontal(
                            *(
                                [
                                    Link(
                                        (
                                            "Copied"
                                            if self._copied_section == (self._payload_format, index)
                                            else "Copy"
                                        ),
                                        url = (
                                            None
                                            if self._copied_section == (self._payload_format, index)
                                            else f"action://copy/{index}"
                                        ),
                                        id = f"copy-{index}",
                                        classes = (
                                            "copy-link is-active"
                                            if self._copied_section == (self._payload_format, index)
                                            else "copy-link"
                                        ),
                                    )
                                ]
                                if section.copy_text is not None
                                else []
                            ),
                            classes = "section-controls",
                        ),
                        classes = "section-bar",
                    ),
                    Static(
                        section.body,
                        classes = (
                            "section-content code-content"
                            if section.copy_text is not None
                            else "section-content"
                        ),
                    ),
                    classes = "section-block",
                )
                for index, section in enumerate(self._current_sections())
            ],
            id = "body",
        )
        yield Static(self._footer_panel, classes = "section-block")


def _should_use_textual_echo_view(
    *,
    debug: bool
) -> bool:
    """Return whether `pw echo` should use the interactive Textual viewer."""

    return (
        debug
        and
        TEXTUAL_AVAILABLE
        and sys.stdout.isatty()
        and sys.stdin.isatty()
    )
