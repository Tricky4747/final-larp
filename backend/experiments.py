"""SQLite stats + epsilon-greedy allocation (the 80/20 loop). Owned by Person B, used by Person D."""
import random, sqlite3
from pathlib import Path

class Experiments:
    def __init__(self, path="experiments.db", epsilon=0.2):
        self.path = Path(path).resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.epsilon = epsilon
        self._db_inode = None
        self._open()

    def _open(self):
        self.db = sqlite3.connect(self.path, check_same_thread=False)
        self.db.execute("CREATE TABLE IF NOT EXISTS v(variant TEXT PRIMARY KEY, sends INT DEFAULT 0, replies INT DEFAULT 0, retired INT DEFAULT 0)")
        columns = {row[1] for row in self.db.execute("PRAGMA table_info(v)")}
        if "retired" not in columns:
            self.db.execute("ALTER TABLE v ADD COLUMN retired INT DEFAULT 0")
        self.db.commit()
        self._db_inode = self.path.stat().st_ino

    def _refresh_if_replaced(self):
        try:
            inode = self.path.stat().st_ino
        except FileNotFoundError:
            inode = None
        if inode != self._db_inode:
            self.db.close()
            self._open()

    def register(self, variant):
        self._refresh_if_replaced()
        self.db.execute("INSERT OR IGNORE INTO v(variant) VALUES(?)", (variant,)); self.db.commit()

    def record(self, variant, replied: bool):
        self._refresh_if_replaced()
        self.db.execute("UPDATE v SET sends=sends+1, replies=replies+? WHERE variant=?", (int(replied), variant)); self.db.commit()

    def stats(self):
        self._refresh_if_replaced()
        return {r[0]: {"sends": r[1], "replies": r[2], "rate": r[2] / r[1] if r[1] else 0.0}
                for r in self.db.execute("SELECT variant, sends, replies FROM v")}

    def _active_stats(self):
        self._refresh_if_replaced()
        return {r[0]: {"sends": r[1], "replies": r[2], "rate": r[2] / r[1] if r[1] else 0.0}
                for r in self.db.execute("SELECT variant, sends, replies FROM v WHERE retired=0")}

    def active_stats(self):
        return self._active_stats()

    def retire(self, variant):
        self._refresh_if_replaced()
        self.db.execute("UPDATE v SET retired=1 WHERE variant=?", (variant,)); self.db.commit()

    def winner(self, min_sends=5):
        eligible = {k: s for k, s in self._active_stats().items() if s["sends"] >= min_sends}
        return max(eligible, key=lambda k: eligible[k]["rate"]) if eligible else None

    def allocate(self, n_leads: int) -> list[str]:
        """Return a variant for each lead: ~80% winner, ~20% spread over the rest."""
        variants = list(self._active_stats()); w = self.winner()
        if not w: return [random.choice(variants) for _ in range(n_leads)]  # no winner yet: explore evenly
        others = [v for v in variants if v != w] or [w]
        return [random.choice(others) if random.random() < self.epsilon else w for _ in range(n_leads)]
