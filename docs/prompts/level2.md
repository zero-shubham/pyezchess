# Level 2 — Tactical Vision

Curriculum content for Level 2. Referenced by `get_level_details` when Vishy teaches this level.

---

## Topic 2.1 — Basic Mate Patterns

**Core concepts**: Ladder Mate using Two Rooks — two rooks alternate delivering check, pushing the enemy King to the edge rank by rank until checkmate. Neither rook is ever left undefended. King + Queen mate — the King is driven to the edge by the Queen while your King escorts from a distance to cut off escape squares, culminating in a mating net. Stalemate traps are a common beginner mistake.

**Teaching guidelines**: Generate a FEN for each pattern and send it to the app so the student can see the position on the board. Walk through the mating sequence move by move. Ask the student to find the next move before revealing it.

**Common mistakes**: Leaving a rook undefended during the ladder; accidentally delivering stalemate instead of checkmate with King + Queen.

**Example positions**: Set up a ladder mate with Two Rooks vs lone King; set up a King + Queen vs lone King near the edge.

---

## Topic 2.2a — The "Big Three" Tactics: Fork

**Core concepts**: A fork is one piece attacking two or more enemy targets simultaneously, forcing the opponent to abandon one. The Knight is the most dangerous forking piece because it cannot be blocked. Queens, pawns, bishops, and rooks can also fork. Common targets: King + Queen (royal fork), King + Rook.

**Teaching guidelines**: Generate FEN positions illustrating fork opportunities. Present the position and ask "can you spot the fork?" before revealing the answer. Show at least one Knight fork and one pawn fork example.

**Common mistakes**: Missing Knight forks because the L-shape is hard to visualize; not noticing a pawn can fork two pieces.

**Example positions**: Place a Knight where it attacks both enemy King and Queen; place a pawn so its next advance forks two minor pieces.

---

## Topic 2.2b — The "Big Three" Tactics: Pin

**Core concepts**: A pin restricts a piece from moving because a more valuable piece sits behind it along the same line. An absolute pin is against the King — the pinned piece cannot move legally. A relative pin is against any other valuable piece — the piece can move but doing so loses material.

**Teaching guidelines**: Generate FEN positions with clear pins. Distinguish absolute from relative pins. Explain how to exploit a pin by piling pressure onto the pinned piece. Ask the student to identify the pinned piece and why it cannot or should not move.

**Common mistakes**: Moving a piece in an absolute pin (illegal); failing to exploit a relative pin by attacking the pinned piece again.

**Example positions**: Bishop pinning a Knight to the King on the e-file; Rook pinning a Bishop to the Queen on the c-file.

---

## Topic 2.2c — The "Big Three" Tactics: Skewer

**Core concepts**: A skewer forces a valuable piece to move and leave a teammate behind it exposed to capture. It is the reverse of a pin — the valuable piece is in front, not behind. A common example: a Rook skewers the enemy King, the King must move, and the Rook captures the Queen behind it.

**Teaching guidelines**: Generate FEN positions with clear skewer opportunities. Contrast with a pin so the distinction is clear. Ask the student to find the skewer before revealing.

**Common mistakes**: Confusing a skewer with a pin; missing skewers along ranks, files, and diagonals.

**Example positions**: Rook on the same file as enemy King and Queen; Bishop on the same diagonal as enemy King and a loose piece.

---

## Topic 2.3 — Defensive Tactics

**Core concepts**: When facing a threat, a defender has three classes of response — the C.B.M. framework: Capture the attacker, Block the path (interpose a piece between attacker and target; only works against sliding pieces), and Move away (relocate the threatened piece). The best defense is not always the most obvious one.

**Teaching guidelines**: Generate FEN positions where the student is under a specific threat. Present each C.B.M. option one at a time and ask the student to evaluate which is best. Reveal the evaluation with reasoning.

**Common mistakes**: Automatically moving away without checking if capturing or blocking is better; trying to block a Knight or pawn attack (non-sliding pieces).

**Example positions**: Position where capturing the attacker is best; position where blocking wins a tempo; position where moving away is the only legal defense.

---

## Topic 2.4 — Board Awareness

**Core concepts**: Unprotected piece scanning — before every move, scan the entire board for pieces that have no defenders. These "hanging" pieces are free captures waiting to happen. Finding hanging pieces for both sides is a pre-move checklist habit, not a one-time skill.

**Teaching guidelines**: Generate FEN positions with multiple hanging pieces of varying subtlety. Ask the student to list all hanging pieces they can find. Reveal any they missed. Reinforce this as a habit to apply before every move.

**Common mistakes**: Only looking at their own hanging pieces and not the opponent's; missing hanging pieces that are visually blocked by other pieces.

**Example positions**: A cluttered middlegame position with 2–3 hanging pieces on both sides; a position where a piece appears defended but the defender is pinned.
