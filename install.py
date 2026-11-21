#!/usr/bin/env python3
"""Small offline user installation; GTK comes from the operating system."""
import argparse
from pathlib import Path
import shutil
import stat
import tempfile
import sys

MARKER = '# Retro Notes user installation v1'


def install_file(path, data, mode):
    fd, temporary = tempfile.mkstemp(dir=path.parent)
    try:
        with open(fd, 'wb') as stream:
            stream.write(data)
        Path(temporary).chmod(mode)
        Path(temporary).replace(path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def main(argv=None):
    parser = argparse.ArgumentParser(description='Install Retro Notes without root or network access')
    parser.add_argument('--prefix', type=Path, default=Path.home() / '.local')
    parser.add_argument('--uninstall', action='store_true')
    args = parser.parse_args(argv)
    prefix = args.prefix.expanduser().resolve()
    library = prefix / 'share' / 'retronotes'
    launcher = prefix / 'bin' / 'rnote'
    marker = library / '.retronotes-install'
    package = library / 'retronotes'
    try:
        for target in (library.parent, launcher.parent, library, launcher, marker, package):
            if target.is_symlink():
                raise OSError(f'Refusing symlink installation target: {target}')
        if library.exists() and (not marker.is_file() or marker.read_text() != MARKER):
            raise OSError(f'Refusing unrelated directory: {library}')
        if launcher.exists():
            if not stat.S_ISREG(launcher.lstat().st_mode):
                raise OSError(f'Refusing unrelated command: {launcher}')
            with launcher.open('rb') as stream:
                stream.readline(4096)
                if stream.readline(4096).rstrip(b'\n') != MARKER.encode():
                    raise OSError(f'Refusing unrelated command: {launcher}')
        if args.uninstall:
            if launcher.exists():
                launcher.unlink()
            if library.exists():
                shutil.rmtree(library)
            print('Retro Notes removed; notes were preserved.')
            return 0
        library.mkdir(parents=True, exist_ok=True)
        install_file(marker, MARKER.encode(), 0o644)
        package.mkdir(exist_ok=True)
        for module in sorted((Path(__file__).resolve().parent / 'retronotes').glob('*.py')):
            install_file(package / module.name, module.read_bytes(), 0o644)
        launcher.parent.mkdir(parents=True, exist_ok=True)
        script = (f'#!{sys.executable}\n{MARKER}\nimport sys\nsys.path.insert(0, {str(library)!r})\n'
                  'from retronotes.__main__ import main\nraise SystemExit(main())\n')
        install_file(launcher, script.encode(), 0o755)
        print(f'Installed {launcher}\nAdd {launcher.parent} to PATH if necessary. GTK 4 / PyGObject must be installed.')
        return 0
    except (OSError, UnicodeError) as error:
        parser.exit(1, f'install: {error}\n')


if __name__ == '__main__':
    raise SystemExit(main())
