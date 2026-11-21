"""Visual-only interpolation. Native GTK insertion marks remain the source of truth."""
from dataclasses import dataclass


@dataclass(frozen=True)
class CaretPosition:
    x: float
    y: float
    height: float


class CaretMotion:
    DURATION_US = 55_000

    def __init__(self):
        self.position = self.target = self.origin = None
        self.started = self.deadline = 0
        self.active = False

    def reset(self):
        self.position = self.target = self.origin = None
        self.active = False

    def sample(self, now):
        if not self.active:
            return self.position
        if now >= self.deadline:
            self.position = self.target
            self.active = False
            return self.position
        elapsed = max(0, now-self.started) / (self.deadline-self.started)
        ease = 1-(1-elapsed)**3
        self.position = CaretPosition(self.origin.x+(self.target.x-self.origin.x)*ease,
                                      self.origin.y+(self.target.y-self.origin.y)*ease,
                                      self.target.height)
        return self.position

    def update(self, target, now, snap=False):
        current = self.sample(now)
        if target == self.target and not snap:
            return current
        # Large jumps, line-height changes and excessive visual lag snap precisely.
        height = max(1, target.height)
        snap = (snap or current is None or abs(current.x-target.x) > 3*height
                or abs(current.y-target.y) > 1.5*height or abs(current.height-target.height) > 1)
        if snap:
            self.position = self.target = self.origin = target
            self.active = False
            return target
        # Retarget the current position, keeping the existing deadline. No queued moves,
        # and repeated key events cannot indefinitely push completion into the future.
        deadline = self.deadline if self.active else now+self.DURATION_US
        self.origin = current
        self.target = target
        self.started = now
        self.deadline = deadline
        self.active = current != target
        return current
