"""
Music trivia game logic.
Plays 30s clips and asks users to guess the song.
"""
import random
import logging
from dataclasses import dataclass, field
from typing import Optional

log = logging.getLogger(__name__)


@dataclass
class TriviaQuestion:
    """A trivia question."""
    track_id: int
    title: str
    artist: str
    preview_url: str
    options: list[str] = field(default_factory=list)  # 4 options including correct
    correct_index: int = 0


@dataclass
class TriviaSession:
    """Active trivia session for a user."""
    user_id: int
    current_question: Optional[TriviaQuestion] = None
    attempts: int = 0
    max_attempts: int = 3
    score: int = 0
    questions_asked: int = 0


# In-memory active sessions
active_sessions: dict[int, TriviaSession] = {}


def generate_options(correct_title: str, all_tracks: list[dict], num_options: int = 4) -> list[str]:
    """
    Generate multiple choice options including the correct answer.
    Shuffles the options.
    """
    options = [correct_title]

    # Get other track titles
    other_titles = [t.get("title", "") for t in all_tracks if t.get("title") != correct_title]

    # Add random options
    while len(options) < num_options and other_titles:
        idx = random.randint(0, len(other_titles) - 1)
        option = other_titles.pop(idx)
        if option and option not in options:
            options.append(option)

    # If we still need more options, add generic ones
    generic = ["Unknown Song", "Mystery Track", "Hidden Gem", "Classic Hit"]
    while len(options) < num_options:
        opt = random.choice(generic)
        if opt not in options:
            options.append(opt)

    # Shuffle
    random.shuffle(options)

    return options


def create_trivia_question(
    track: dict,
    all_tracks: list[dict],
) -> TriviaQuestion:
    """Create a trivia question from a track."""
    options = generate_options(track.get("title", ""), all_tracks)
    correct_index = options.index(track.get("title", ""))

    return TriviaQuestion(
        track_id=track.get("track_id", 0),
        title=track.get("title", ""),
        artist=track.get("artist", ""),
        preview_url=track.get("preview_url", ""),
        options=options,
        correct_index=correct_index,
    )


def start_session(user_id: int) -> TriviaSession:
    """Start or reset a trivia session for a user."""
    session = TriviaSession(user_id=user_id)
    active_sessions[user_id] = session
    log.info("[TRIVIA] start_session user=%s (active sessions: %d)", user_id, len(active_sessions))
    return session


def get_session(user_id: int) -> Optional[TriviaSession]:
    """Get active trivia session for a user."""
    return active_sessions.get(user_id)


def end_session(user_id: int):
    """End a trivia session."""
    removed = active_sessions.pop(user_id, None)
    log.info("[TRIVIA] end_session user=%s (had_session=%s)", user_id, removed is not None)


def check_answer(session: TriviaSession, answer_index: int) -> tuple[bool, str]:
    """
    Check if the answer is correct.
    Returns (is_correct, message).
    """
    if not session.current_question:
        return False, "No active question."

    session.attempts += 1

    if answer_index == session.current_question.correct_index:
        # Correct!
        points = max(10 - (session.attempts - 1) * 3, 1)  # More points for fewer attempts
        session.score += points
        session.questions_asked += 1

        log.info("[TRIVIA] user=%s CORRECT (attempt %d) +%d pts, score=%d",
                 session.user_id, session.attempts, points, session.score)
        msg = f"✅ Correct! +{points} points"
        session.current_question = None
        session.attempts = 0
        return True, msg
    else:
        # Wrong
        remaining = session.max_attempts - session.attempts
        if remaining > 0:
            log.info("[TRIVIA] user=%s wrong, %d attempts left", session.user_id, remaining)
            correct = session.current_question.correct_index + 1
            return False, f"❌ Wrong! {remaining} attempts left. Try again!"
        else:
            # Out of attempts
            correct_title = session.current_question.options[session.current_question.correct_index]
            correct_artist = session.current_question.artist
            session.questions_asked += 1
            session.current_question = None
            session.attempts = 0

            log.info("[TRIVIA] user=%s OUT OF ATTEMPTS, answer was: %s - %s", session.user_id, correct_title, correct_artist)
            return False, f"❌ Out of attempts! The answer was: {correct_title} - {correct_artist}"


def format_question(question: TriviaQuestion) -> str:
    """Format a trivia question for display."""
    lines = [
        "🎵 <b>Guess the Song!</b>",
        "",
        f"🎤 Artist: <b>{question.artist}</b>",
        "",
        "Choose the correct song title:",
    ]

    for i, option in enumerate(question.options, 1):
        lines.append(f"{i}. {option}")

    lines.append("")
    lines.append("Send the number (1-4) of your answer")

    return "\n".join(lines)


def format_session_stats(session: TriviaSession) -> str:
    """Format trivia session stats."""
    lines = [
        "📊 <b>Your Trivia Stats</b>",
        "",
        f"🎯 Score: {session.score}",
        f"❓ Questions: {session.questions_asked}",
        f"🔥 Streak: {session.attempts}",
    ]
    return "\n".join(lines)
