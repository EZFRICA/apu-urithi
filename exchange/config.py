"""Where the question box keeps its questions, and the meter its counts. Its own directory: neither side's."""

import os

_HERE = os.path.dirname(os.path.abspath(__file__))

DATA_DIR = os.environ.get("EXCHANGE_DATA_DIR", os.path.join(_HERE, "data"))
QUESTIONS_PATH = os.environ.get("EXCHANGE_QUESTIONS_PATH", os.path.join(DATA_DIR, "questions.sqlite3"))
COUNTERS_PATH = os.environ.get("EXCHANGE_COUNTERS_PATH", os.path.join(DATA_DIR, "counters.sqlite3"))
