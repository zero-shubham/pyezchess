from __future__ import annotations

import chess

from domain.game.board import EzBoard


# FEN: early middlegame from Italian Game where captures are possible
# r1bqkb1r/pppp1ppp/2n2n2/4p3/2B1P3/5N2/PPPP1PPP/RNBQK2R w KQkq - 4 4
ITALIAN_FEN = "r1bqkb1r/pppp1ppp/2n2n2/4p3/2B1P3/5N2/PPPP1PPP/RNBQK2R w KQkq - 4 4"


class TestEzBoardBasicCapture:
    def test_white_captures_multiple(self) -> None:
        board = EzBoard(ITALIAN_FEN)
        board.push(chess.Move.from_uci("c4f7"))  # Bxf7+ (captures pawn)

        assert board.captured["white"] == ["p"]
        assert board.captured["black"] == []

    def test_both_sides_capture(self) -> None:
        board = EzBoard("r1bqkb1r/pppp1ppp/2n2n2/4p3/2B1P3/5N2/PPPP1PPP/RNBQ1RK1 b kq - 5 4")
        board.push(chess.Move.from_uci("f6e4"))  # Nxe4 (black captures pawn)
        board.push(chess.Move.from_uci("f1e1"))  # Re1
        board.push(chess.Move.from_uci("e4f2"))  # Nxf2 (black captures another pawn)

        assert board.captured["black"] == ["P", "P"]
        assert board.captured["white"] == []

    def test_pawn_captures_pawn(self) -> None:
        board = EzBoard("rnbqkbnr/ppp1pppp/8/3p4/4P3/8/PPPP1PPP/RNBQKBNR w KQkq d6 0 2")
        board.push(chess.Move.from_uci("e4d5"))  # exd5

        assert board.captured["white"] == ["p"]
        assert board.captured["black"] == []


class TestEzBoardEnPassant:
    def test_en_passant_capture(self) -> None:
        board = EzBoard("rnbqkbnr/ppp2ppp/8/3Pp3/8/8/PPPP1PPP/RNBQKBNR w KQkq e6 0 3")
        board.push(chess.Move.from_uci("d5e6"))  # dxe6 (en passant)

        assert board.captured["white"] == ["p"]
        assert board.captured["black"] == []

    def test_black_en_passant_capture(self) -> None:
        board = EzBoard("rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq e3 0 1")
        board.push(chess.Move.from_uci("d7d5"))  # d5
        board.push(chess.Move.from_uci("e4e5"))  # e5
        board.push(chess.Move.from_uci("f7f5"))  # f5
        board.push(chess.Move.from_uci("e5f6"))  # exf6 (en passant)

        assert board.captured["white"] == ["p"]
        assert board.captured["black"] == []


class TestEzBoardResetAndSerialize:
    def test_reset_clears_captures(self) -> None:
        board = EzBoard("rnbqkbnr/ppp1pppp/8/3p4/4P3/8/PPPP1PPP/RNBQKBNR w KQkq d6 0 2")
        board.push(chess.Move.from_uci("e4d5"))  # exd5
        assert board.captured["white"] == ["p"]

        board.reset()
        assert board.captured["white"] == []
        assert board.captured["black"] == []

    def test_set_captured_restores_state(self) -> None:
        board = EzBoard()
        board.set_captured({"white": ["p", "n"], "black": ["P"]})
        assert board.captured["white"] == ["p", "n"]
        assert board.captured["black"] == ["P"]

    def test_set_captured_empty_defaults(self) -> None:
        board = EzBoard()
        board.set_captured({})
        assert board.captured["white"] == []
        assert board.captured["black"] == []

    def test_captured_returns_list_not_ref(self) -> None:
        board = EzBoard("rnbqkbnr/ppp1pppp/8/3p4/4P3/8/PPPP1PPP/RNBQKBNR w KQkq d6 0 2")
        board.push(chess.Move.from_uci("e4d5"))  # exd5

        captured = board.captured
        captured["white"].append("x")

        assert "x" not in board.captured["white"]

    def test_set_captured_returns_list_not_ref(self) -> None:
        data: dict[str, list[str]] = {"white": ["p"], "black": []}
        board = EzBoard()
        board.set_captured(data)
        data["white"].append("x")

        assert board.captured["white"] == ["p"]


class TestEzBoardCallback:
    def test_on_captured_callback_fires(self) -> None:
        call_count = 0

        def on_capture() -> None:
            nonlocal call_count
            call_count += 1

        board = EzBoard("r1bqkb1r/pppp1ppp/2n2n2/4p3/2B1P3/5N2/PPPP1PPP/RNBQK2R w KQkq - 4 4")
        board.on_captured = on_capture

        board.push(chess.Move.from_uci("c4f7"))  # Bxf7+ (capture)

        assert call_count == 1

    def test_on_captured_not_called_for_non_capture(self) -> None:
        call_count = 0

        def on_capture() -> None:
            nonlocal call_count
            call_count += 1

        board = EzBoard()
        board.on_captured = on_capture
        board.push(chess.Move.from_uci("e2e4"))  # e4

        assert call_count == 0
