from colorama import Fore, Back, Style
from typing import Callable, NoReturn

class TextStream:
    def __init__(self, text:str):
        self._left:str = ''
        self._right:str = text
        self._full:str = text

    @property
    def pos(self) -> int:
        """Absolute position in string."""
        return len(self._left)

    @pos.setter
    def pos(self, pos:int):
        if not 0 <= pos <= len(self.full):
            raise ValueError('pos out of range.')

        self._left = self.full[:pos]
        self._right = self.full[pos:]

    @property
    def full(self) -> str:
        """Full text. Left+Right."""
        return self._full

    @full.setter
    def full(self, full:str):
        if self.pos > len(full):
            raise ValueError('Stream position is outside new full text.')

        self._left = full[:self.pos]
        self._right = full[self.pos:]
        self._full = full

    def seek(self, n:int):
        """Set absolute position in string."""
        self.pos = n

    def consume(self, n:int=1) -> str:
        """Consume n characters. Returns consumed text."""
        consumed = self.peek(n)
        self.pos += len(consumed)
        return consumed

    def consume_text(self, text:str) -> bool:
        if self.match(text):
            self.consume(len(text))
            return True
        return False

    def consume_until(self, text:str) -> str:
        """Consume until text. Returns consumed text."""
        start = self.pos
        index = self._right.find(text)

        if index == -1:
            self.pos = len(self.full)
        else:
            self.pos += index

        return self.full[start:self.pos]

    def consume_while(self, predicate: Callable[[str], bool]) -> str:
        start = self.pos
        while self and predicate(self.peek()):
            self.consume()
        return self.full[start:self.pos]

    def consume_word(self) -> str:
        return self.consume_while(lambda c: c.isalnum() or c == '_')

    def consume_whitespace(self, newline=True) -> str:
        if newline:
            return self.consume_while(lambda c: c.isspace())
        else:
            return self.consume_while(lambda c: c.isspace() and c != '\n')

    def match(self, text:str) -> bool:
        """Return if given text matches next chars in self.right."""
        return self._right.startswith(text)

    def peek(self, n:int=1) -> str:
        return self._right[:n]

    @property
    def eof(self) -> bool:
        return not self._right

    @property
    def remaining(self) -> str:
        """Remaining characters on the right side."""
        return self._right

    # These should never be written to.
    # It would break self.full.
    @property
    def left(self) -> str:
        return self._left

    @property
    def right(self) -> str:
        return self._right

    @property
    def line(self) -> int:
        """Current line number (1-based)."""
        return self.full.count('\n', 0, self.pos) + 1

    @property
    def column(self) -> int:
        return len(self.left.rpartition('\n')[2]) + 1

    @property
    def current_line(self) -> str:
        return (
            self.left.rpartition('\n')[2] +
            self.right.partition('\n')[0]
        )

    def error(self, error:str, text:str, highlight=None) -> NoReturn:
        print(self.current_line)
        if not highlight:
            print(' '*(self.column-1)+'^')
        else:
            l = self.current_line.find(highlight)
            print(' '*l+'^'*len(highlight))

        print(f'{Fore.RED}{Style.BRIGHT}{Back.BLACK}{error}: {text}', Style.RESET_ALL)
        print(f'At line {self.line}, col {self.column}')
        exit(-1)

    def expect(self, text:str):
        if not self.consume_text(text):
            self.error('SyntaxError', f"Expected '{text}'")

    def __str__(self) -> str:
        return self.full

    def __bool__(self) -> bool:
        return not self.eof

    def __contains__(self, item: str) -> bool:
        return item in self.full

    def __iadd__(self, other: str):
        self.full += other
        return self

    def __eq__(self, other: object) -> bool:
        if isinstance(other, TextStream):
            return self.full == other.full
        if isinstance(other, str):
            return self.full == other
        return NotImplemented

    def __repr__(self) -> str:
        return (
            f"TextStream(pos={self.pos}, "
            f"left={self.left!r}, "
            f"right={self.right!r})"
        )
