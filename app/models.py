# app/models.py
from datetime import datetime, timezone
from .constants import DEFAULT_EXCHANGE, DEFAULT_CATEGORY
from .extensions import db

# -------- Detection Rules --------
class DetectionRule(db.Model):
    __tablename__ = "detection_rules"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(32), nullable=False)
    lookback_min = db.Column(db.Integer, nullable=False)
    threshold_pct = db.Column(db.Float, nullable=False)
    color = db.Column(db.String(16), nullable=False, default="#10b981")
    sound_file = db.Column(db.String(64), nullable=True)
    enabled = db.Column(db.Boolean, nullable=False, default=True)
    sort_order = db.Column(db.Integer, nullable=False, default=0)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False,
                           default=lambda: datetime.now(timezone.utc))

    def __repr__(self) -> str:
        return f"<DetectionRule {self.name!r} {self.threshold_pct}%/{self.lookback_min}m>"


# -------- Signals --------
class Signal(db.Model):
    __tablename__ = "signals"

    id = db.Column(db.Integer, primary_key=True)
    exchange = db.Column(db.String(16), nullable=False, default=DEFAULT_EXCHANGE)
    symbol = db.Column(db.String(48), nullable=False, index=True)
    rule_id = db.Column(db.Integer, db.ForeignKey("detection_rules.id"), nullable=True)
    rule_label = db.Column(db.String(32), nullable=True)       # snapshot: "0.5%/2m"
    rule_color = db.Column(db.String(16), nullable=True)       # snapshot: "#10b981"
    change_pct = db.Column(db.Float, nullable=False, default=0) # abs change in percent, e.g. 5.23
    window = db.Column(db.String(8), nullable=False)           # example: '5m', '15m', '1h'
    price = db.Column(db.Float, nullable=True)
    event_ts = db.Column(db.DateTime(timezone=True), nullable=False, index=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False,
                           default=lambda: datetime.now(timezone.utc))

    rule = db.relationship("DetectionRule")

    def __repr__(self) -> str:
        label = self.rule.name if self.rule else "?"
        return f"<Signal {self.symbol} {label} {self.change_pct}% {self.window} @ {self.event_ts}>"

# -------- Deduplication of Signals --------
class SignalDedup(db.Model):
    __tablename__ = "signal_dedup"

    # Composite primary key: key
    key = db.Column(db.String(128), primary_key=True)
    last_at = db.Column(db.DateTime(timezone=True), nullable=False)

    def __repr__(self) -> str:
        return f"<SignalDedup {self.key} at {self.last_at}>"

# -------- Age of Symbols --------
class SymbolAge(db.Model):
    __tablename__ = "symbol_age"
    symbol = db.Column(db.String(48), primary_key=True)
    category = db.Column(db.String(16), primary_key=True, default=DEFAULT_CATEGORY)

    # Earliest daily kline ts (milliseconds, UTC)
    first_ts = db.Column(db.BigInteger, nullable=False)
    first_day = db.Column(db.Date, nullable=False)

    checked_at = db.Column(db.DateTime(timezone=True), nullable=False,
                           default=lambda: datetime.now(timezone.utc))
    source = db.Column(db.String(32), nullable=False, default=DEFAULT_EXCHANGE)

    def __repr__(self) -> str:
        return f"<SymbolAge {self.symbol}/{self.category} first={self.first_day}>"

# -------- Key-Value Settings --------
class Setting(db.Model):
    __tablename__ = "settings_kv"

    key = db.Column(db.String(64), primary_key=True)
    value = db.Column(db.Text, nullable=True)
    updated_at = db.Column(db.DateTime(timezone=True), nullable=False,
                           default=lambda: datetime.now(timezone.utc))

    def __repr__(self) -> str:
        return f"<Setting {self.key}={self.value!r}>"
