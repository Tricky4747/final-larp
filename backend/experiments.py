"""SQLite stats + epsilon-greedy allocation (the 80/20 loop). Owned by Person B, used by Person D."""
import sqlite3, random

class Experiments:
    def __init__(self, path="experiments.db", epsilon=0.2):
        self.db = sqlite3.connect(path, check_same_thread=False); self.epsilon = epsilon
        self.db.execute("CREATE TABLE IF NOT EXISTS v(variant TEXT PRIMARY KEY, sends INT DEFAULT 0, replies INT DEFAULT 0)")

    def register(self, variant):
        self.db.execute("INSERT OR IGNORE INTO v(variant) VALUES(?)", (variant,)); self.db.commit()

    def record(self, variant, replied: bool):
        self.db.execute("UPDATE v SET sends=sends+1, replies=replies+? WHERE variant=?", (int(replied), variant)); self.db.commit()

    def stats(self):
        return {r[0]: {"sends": r[1], "replies": r[2], "rate": r[2] / r[1] if r[1] else 0.0}
                for r in self.db.execute("SELECT variant, sends, replies FROM v")}

    def winner(self, min_sends=5):
        eligible = {k: s for k, s in self.stats().items() if s["sends"] >= min_sends}
        return max(eligible, key=lambda k: eligible[k]["rate"]) if eligible else None

    def allocate(self, n_leads: int) -> list[str]:
        """Return a variant for each lead: ~80% winner, ~20% spread over the rest."""
        variants = list(self.stats()); w = self.winner()
        if not w: return [random.choice(variants) for _ in range(n_leads)]  # no winner yet: explore evenly
        others = [v for v in variants if v != w] or [w]
        return [random.choice(others) if random.random() < self.epsilon else w for _ in range(n_leads)]
