"""Plain Markdown storage and semantic palette; independent of GTK."""
import os
from pathlib import Path
import re
import stat
import tempfile
import tomllib
import time
import unicodedata
from datetime import datetime

DEFAULT = dict(background='#101916', foreground='#b9dac3', accent='#91e5ad', warning='#e4bc78', critical='#e68c80')


def theme_paths():
    return [Path(os.environ.get(env, Path.home() / default)) / 'omarchy/current/theme/colors.toml'
            for env, default in [('XDG_STATE_HOME', '.local/state'), ('XDG_CONFIG_HOME', '.config')]]


def palette(paths=None):
    for path in paths if paths is not None else theme_paths():
        try:
            data = tomllib.loads(path.read_text())
            result = DEFAULT.copy()
            for role, aliases in {'background': ('background', 'color0'), 'foreground': ('foreground', 'color7'),
                                  'accent': ('accent', 'blue', 'color4'), 'warning': ('warning', 'yellow', 'color3'),
                                  'critical': ('critical', 'red', 'color1')}.items():
                for key in aliases:
                    value = data.get(key)
                    if isinstance(value, str) and re.fullmatch(r'#[\da-fA-F]{6}', value):
                        result[role] = value
                        break
            return result
        except (OSError, ValueError):
            pass
    return DEFAULT.copy()


STAMP = re.compile(r'^(\d{4}-\d{2}-\d{2}_\d{6})__(.+)$')


def default_notes_dir():
    return Path.home() / 'Notes'


def safe_title(title):
    text = unicodedata.normalize('NFKC', title)
    text = re.sub(r'[^\w]+', '-', text, flags=re.UNICODE).strip('-_')
    text = text.encode('utf-8')[:160].decode('utf-8', errors='ignore').rstrip('-_')
    return text or 'Untitled'


def note_identity(path):
    match = STAMP.match(path.stem)
    if match:
        try:
            date = datetime.strptime(match[1], '%Y-%m-%d_%H%M%S')
            return date, match[2].replace('-', ' ')
        except ValueError:
            pass
    return datetime.fromtimestamp(path.lstat().st_mtime), path.stem


class DeleteConfirmation:
    """A second request for the same unchanged file must arrive within four seconds."""
    def __init__(self, clock=time.monotonic):
        self.clock = clock
        self.cancel()

    def cancel(self):
        self.pending = None
        self.deadline = 0

    def request(self, path):
        stat = path.stat()
        identity = (path, stat.st_ino, stat.st_mtime_ns, stat.st_size)
        confirmed = self.pending == identity and self.clock() < self.deadline
        self.cancel()
        if not confirmed:
            self.pending = identity
            self.deadline = self.clock() + 4
        return confirmed


class SaveConflict(OSError):
    pass


class Store:
    def __init__(self, root):
        self.root = Path(root).expanduser().resolve()
        self.root.mkdir(mode=0o700, parents=True, exist_ok=True)

    def notes(self, query=''):
        def matches(name):
            chars = iter(name.casefold())
            return all(any(c == x for c in chars) for x in query.casefold())
        return sorted((p for p in self.root.glob('*.md') if not p.is_symlink() and p.is_file() and matches(p.name)),
                      key=lambda p: (note_identity(p)[0], p.name), reverse=True)

    @staticmethod
    def candidates(directory, stem):
        for n in range(10000):
            yield directory / (stem + (f'--{n+1}' if n else '') + '.md')

    def create(self, quick=False, title=''):
        stem = datetime.now().strftime('%Y-%m-%d_%H%M%S__') + safe_title('Capture' if quick else title)
        for path in self.candidates(self.root, stem):
            try:
                os.close(os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600))
                return path
            except FileExistsError:
                continue
        raise OSError('Cannot allocate note filename')

    def managed(self, path):
        path = Path(path).absolute()
        if path.parent != self.root or path.suffix != '.md':
            raise OSError('Only Markdown files in the notes directory are supported')
        if not stat.S_ISREG(path.lstat().st_mode):
            raise OSError('Only regular notes are supported')
        return path

    @staticmethod
    def fingerprint(info):
        return info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns

    def stamp(self, path):
        return self.fingerprint(self.managed(path).lstat())

    def read(self, path):
        path = self.managed(path)
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(fd, 'r', encoding='utf-8') as stream:
            if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
                raise OSError('Only regular notes are supported')
            return stream.read()

    @staticmethod
    def move_unique(source, directory, stem):
        # Hard-link + unlink provides no-clobber moves on the same filesystem.
        for target in Store.candidates(directory, stem):
            if target == source:
                return source
            try:
                os.link(source, target, follow_symlinks=False)
            except FileExistsError:
                continue
            try:
                source.unlink()
            except OSError:
                target.unlink()
                raise
            return target
        raise OSError('Cannot allocate destination filename')

    def rename(self, path, title):
        path = self.managed(path)
        date, _ = note_identity(path)
        return self.move_unique(path, self.root, date.strftime('%Y-%m-%d_%H%M%S__') + safe_title(title))

    def trash(self, path):
        path = self.managed(path)
        directory = self.root / '.trash'
        if directory.is_symlink():
            raise OSError('Trash directory must not be a symlink')
        directory.mkdir(mode=0o700, exist_ok=True)
        return self.move_unique(path, directory, path.stem)

    def save(self, path, text, expected=None):
        path = self.managed(path)
        source = os.open(path, os.O_WRONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        try:
            info = os.fstat(source)
            if not stat.S_ISREG(info.st_mode):
                raise OSError('Only regular notes are supported')
            initial = self.fingerprint(info)
            if expected is not None and initial != expected:
                raise SaveConflict()
            mode = stat.S_IMODE(info.st_mode) & 0o777
        finally:
            os.close(source)

        fd, temporary = tempfile.mkstemp(prefix='.' + path.name, dir=path.parent)
        try:
            with os.fdopen(fd, 'w', encoding='utf-8', newline='') as stream:
                stream.write(text)
                stream.flush()
                os.fchmod(stream.fileno(), mode)
                os.fsync(stream.fileno())
                if self.stamp(path) != initial:
                    raise SaveConflict()
                os.replace(temporary, path)
                saved = self.fingerprint(os.fstat(stream.fileno()))
            directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
            return saved
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)
