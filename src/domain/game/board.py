from __future__ import annotations

import logging
from collections.abc import Callable

import chess
from chess import Board, Move

logger = logging.getLogger(__name__)


class EzBoard(Board):

    def __init__(self, fen: str = chess.STARTING_FEN, chess960: bool = False) -> None:
        super().__init__(fen, chess960=chess960)
        self.white_captured: list[str] = []
        self.black_captured: list[str] = []
        self._capture_records: list[bool | None] = []
        self.on_captured: Callable[[], None] | None = None

    @property
    def captured(self) -> dict[str, list[str]]:
        return {
            "white": list(self.white_captured),
            "black": list(self.black_captured),
        }

    def set_captured(self, data: dict[str, list[str]]) -> None:
        self.white_captured = list(data.get("white", []))
        self.black_captured = list(data.get("black", []))

    def reset(self) -> None:
        super().reset()
        self.white_captured = []
        self.black_captured = []
        self._capture_records = []

    def push(self, move: Move) -> None:
        captured = False
        if self.is_capture(move):
            captured_piece = None
            if self.is_en_passant(move):
                captured_piece = chess.Piece(chess.PAWN, not self.turn)
            else:
                captured_piece = self.piece_at(move.to_square)

            if captured_piece:
                symbol = captured_piece.symbol()
                if self.turn == chess.WHITE:
                    logger.info("appending %r to white_captured (previous: %s)", symbol, self.white_captured)
                    self.white_captured.append(symbol)
                else:
                    logger.info("appending %r to black_captured (previous: %s)", symbol, self.black_captured)
                    self.black_captured.append(symbol)
                captured = True

                if self.on_captured:
                    self.on_captured()

        self._capture_records.append(self.turn == chess.WHITE if captured else None)
        return super().push(move)

    def get_legal_moves_san(self) -> list[str]:
        san_board = Board(self.fen())
        return [san_board.san(m) for m in self.legal_moves]

    def pop(self) -> Move:
        if self._capture_records:
            record = self._capture_records.pop()
            if record is not None:
                (self.white_captured if record else self.black_captured).pop()
        return super().pop()
