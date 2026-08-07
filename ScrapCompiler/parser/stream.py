from contextlib import contextmanager
from types import NotImplementedType
from typing import Any, Callable, NoReturn

from colorama import Back, Fore, Style


class TextStream:
    """Provide cursor-based text consumption with source-location metadata."""

    def __init__(self, text: str, debug: bool = True) -> None:
        """Create a stream for ``text`` and configure debug metadata emission."""
        self._left: str = ""
        self._right: str = text
        self._full: str = text
        self._debug = debug
        self._range_start: int | None = None

    @property
    def pos(self) -> int:
        """Absolute position in string."""
        return len(self._left)

    @pos.setter
    def pos(self, pos: int) -> None:
        """Move the cursor to an absolute source position."""
        if not 0 <= pos <= len(self.full):
            raise ValueError("pos out of range.")

        self._left = self.full[:pos]
        self._right = self.full[pos:]

    @property
    def full(self) -> str:
        """Full text. Left+Right."""
        return self._full

    @full.setter
    def full(self, full: str) -> None:
        """Replace the stream text while preserving the cursor position."""
        if self.pos > len(full):
            raise ValueError("Stream position is outside new full text.")

        self._left = full[: self.pos]
        self._right = full[self.pos :]
        self._full = full

    def seek(self, n: int) -> None:
        """Set the absolute cursor position in the source string."""
        self.pos = n

    def consume(self, n: int = 1) -> str:
        """Consume and return up to ``n`` characters."""
        consumed = self.peek(n)
        self.pos += len(consumed)
        return consumed

    def consume_text(self, text: str) -> bool:
        """Consume ``text`` when it matches at the current cursor."""
        if self.match(text):
            self.consume(len(text))
            return True
        return False

    def consume_until(self, text: str) -> str:
        """Consume and return text preceding the next ``text`` occurrence."""
        start = self.pos
        index = self._right.find(text)

        if index == -1:
            self.pos = len(self.full)
        else:
            self.pos += index

        return self.full[start : self.pos]

    def consume_while(self, predicate: Callable[[str], bool]) -> str:
        """Consume and return characters while ``predicate`` accepts them."""
        start = self.pos
        while self and predicate(self.peek()):
            self.consume()
        return self.full[start : self.pos]

    def consume_word(self) -> str:
        """Consume and return an alphanumeric or underscore identifier."""
        return self.consume_while(lambda c: c.isalnum() or c == "_")

    def consume_whitespace(self, newline: bool = True) -> str:
        """Consume whitespace, optionally stopping at newlines."""
        if newline:
            return self.consume_while(lambda c: c.isspace())
        else:
            return self.consume_while(lambda c: c.isspace() and c != "\n")

    def match(self, text: str) -> bool:
        """Return whether ``text`` matches the next source characters."""
        return self._right.startswith(text)

    def peek(self, n: int = 1) -> str:
        """Return up to ``n`` upcoming characters without consuming them."""
        return self._right[:n]

    @property
    def eof(self) -> bool:
        """Return whether the cursor has reached the end of input."""
        return not self._right

    @property
    def remaining(self) -> str:
        """Return the unconsumed suffix of the source text."""
        return self._right

    # These should never be written to, so they are read only properties.
    # It would break self.full.
    @property
    def left(self) -> str:
        """Return the consumed prefix of the source text."""
        return self._left

    @property
    def right(self) -> str:
        """Return the unconsumed suffix of the source text."""
        return self._right

    @property
    def line(self) -> int:
        """Return the current one-based line number."""
        return self.full.count("\n", 0, self.pos) + 1

    @property
    def column(self) -> int:
        """Return the current one-based column number."""
        return len(self.left.rpartition("\n")[2]) + 1

    @property
    def current_line(self) -> str:
        """Return the full source line containing the cursor."""
        return self.left.rpartition("\n")[2] + self.right.partition("\n")[0]

    @contextmanager
    def range(self):
        """Context manager that records the start position for range metadata."""
        start = self.pos
        self._range_start = start
        try:
            yield
        finally:
            self._range_start = None

    def emit(self, value: dict[str, Any]) -> dict[str, Any]:
        """Return a node augmented with current source metadata when enabled."""
        if not self._debug:
            return value

        node: dict[str, Any] = value | {
            "line": self.line,
            "column": self.column,
            "error": self.current_line,
        }
        if self._range_start is not None:
            node["range_start"] = self._range_start
            node["range_end"] = self.pos
        return node

    def error(
        self,
        error: str,
        text: str,
        highlight: str | None = None,
    ) -> NoReturn:
        """Print a formatted syntax error and terminate parsing."""
        print(self.current_line)
        if not highlight:
            print(" " * (self.column - 1) + "^")
        else:
            l = self.current_line.find(highlight)
            print(" " * l + "^" * len(highlight))

        print(f"{Fore.RED}{Style.BRIGHT}{Back.BLACK}{error}: {text}", Style.RESET_ALL)
        print(f"At line {self.line}, col {self.column}")
        exit(-1)

    def expect(self, text: str) -> None:
        """Require ``text`` at the cursor or raise a syntax error."""
        if not self.consume_text(text):
            self.error("SyntaxError", f"Expected '{text}'")

    def __str__(self) -> str:
        """Return the original source text."""
        return self.full

    def __bool__(self) -> bool:
        """Return whether unconsumed source text remains."""
        return not self.eof

    def __contains__(self, item: str) -> bool:
        """Return whether ``item`` occurs anywhere in the source text."""
        return item in self.full

    def __iadd__(self, other: str) -> TextStream:
        """Append source text while retaining the current cursor position."""
        self.full += other
        return self

    def __eq__(self, other: object) -> bool | NotImplementedType:
        """Compare the full source text with another stream or string."""
        if isinstance(other, TextStream):
            return self.full == other.full
        if isinstance(other, str):
            return self.full == other
        return NotImplemented

    def __repr__(self) -> str:
        """Return a debug representation of the stream cursor and buffers."""
        return (
            f"TextStream(pos={self.pos}, "
            f"left={self.left!r}, "
            f"right={self.right!r})"
        )
