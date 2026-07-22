from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from functools import lru_cache

import tree_sitter_bash
from tree_sitter import Language, Node, Parser


@dataclass(frozen=True, slots=True)
class BashAst:
    source: bytes
    root: Node

    def text(self, node: Node) -> str:
        return self.source[node.start_byte : node.end_byte].decode("utf-8", "replace")

    def walk(self) -> Iterable[Node]:
        stack = [self.root]
        while stack:
            node = stack.pop()
            yield node
            stack.extend(reversed(node.children))


def parse_bash_ast(command: str) -> BashAst:
    source = str(command or "").encode("utf-8")
    tree = _parser().parse(source)
    return BashAst(source=source, root=tree.root_node)


@lru_cache(maxsize=1)
def _parser() -> Parser:
    language = Language(tree_sitter_bash.language())
    parser = Parser()
    parser.language = language
    return parser
