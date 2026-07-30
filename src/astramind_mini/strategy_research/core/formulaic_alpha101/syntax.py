"""Case-insensitive parser that preserves the paper's decimal tokens."""

from __future__ import annotations

import re
from dataclasses import dataclass

_LEXEME_PATTERN = re.compile(
    r"\s*(?:(?P<number>(?:\d+(?:\.\d*)?|\.\d+))|"
    r"(?P<name>[A-Za-z_][A-Za-z0-9_.]*)|(?P<op>\|\||==|[()+\-*/^,<>=?:]))"
)
_PRECEDENCE = {"||": 1, "==": 2, "<": 2, ">": 2, "+": 3, "-": 3, "*": 4, "/": 4, "^": 5}


@dataclass(frozen=True)
class Lexeme:
    kind: str
    text: str


@dataclass(frozen=True)
class AstNode:
    kind: str
    value: str
    children: tuple[AstNode, ...] = ()

    def canonical(self) -> tuple[str, str, tuple[object, ...]]:
        return self.kind, self.value, tuple(child.canonical() for child in self.children)


def tokenize(source: str) -> tuple[Lexeme, ...]:
    tokens: list[Lexeme] = []
    position = 0
    while position < len(source):
        match = _LEXEME_PATTERN.match(source, position)
        if match is None:
            raise ValueError(f"unexpected formula token at offset {position}")
        kind = match.lastgroup
        if kind is None:
            raise ValueError("formula tokenizer lost token kind")
        tokens.append(Lexeme(kind, match.group(kind)))
        position = match.end()
    return tuple(tokens)


class _Parser:
    def __init__(self, tokens: tuple[Lexeme, ...]) -> None:
        self.tokens = tokens
        self.position = 0

    def parse(self) -> AstNode:
        node = self._expression(0)
        if self.position != len(self.tokens):
            raise ValueError(f"unexpected trailing token {self._peek().text}")
        return node

    def _expression(self, minimum: int) -> AstNode:
        left = self._prefix()
        while self.position < len(self.tokens):
            item = self._peek()
            if item.text == "?" and minimum <= 0:
                self.position += 1
                when_true = self._expression(0)
                self._expect(":")
                left = AstNode("ternary", "?:", (left, when_true, self._expression(0)))
                continue
            precedence = _PRECEDENCE.get(item.text)
            if precedence is None or precedence < minimum:
                break
            self.position += 1
            right = self._expression(precedence if item.text == "^" else precedence + 1)
            left = AstNode("binary", item.text, (left, right))
        return left

    def _prefix(self) -> AstNode:
        item = self._take()
        if item.text in {"+", "-"}:
            return AstNode("unary", item.text, (self._expression(5),))
        if item.text == "(":
            node = self._expression(0)
            self._expect(")")
            return node
        if item.kind == "number":
            return AstNode("number", item.text)
        if item.kind != "name":
            raise ValueError(f"unexpected prefix token {item.text}")
        if self.position >= len(self.tokens) or self._peek().text != "(":
            return AstNode("identifier", item.text.lower())
        self.position += 1
        arguments: list[AstNode] = []
        if self._peek().text != ")":
            while True:
                arguments.append(self._expression(0))
                if self._peek().text != ",":
                    break
                self.position += 1
        self._expect(")")
        return AstNode("call", item.text.lower(), tuple(arguments))

    def _peek(self) -> Lexeme:
        if self.position >= len(self.tokens):
            raise ValueError("unexpected end of formula")
        return self.tokens[self.position]

    def _take(self) -> Lexeme:
        item = self._peek()
        self.position += 1
        return item

    def _expect(self, text: str) -> None:
        item = self._take()
        if item.text != text:
            raise ValueError(f"expected {text}, received {item.text}")


def parse_formula(source: str) -> AstNode:
    return _Parser(tokenize(source)).parse()


def decimal_tokens(source: str) -> tuple[str, ...]:
    return tuple(token.text for token in tokenize(source) if token.kind == "number")


__all__ = ["AstNode", "Lexeme", "decimal_tokens", "parse_formula", "tokenize"]
