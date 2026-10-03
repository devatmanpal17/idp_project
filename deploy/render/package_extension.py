"""Package the installable extension source; exclude browser/local configuration."""
from pathlib import Path
import sys
from zipfile import ZipFile, ZIP_DEFLATED


def package_extension(source: Path, destination: Path):
    with ZipFile(destination, 'w', compression=ZIP_DEFLATED) as bundle:
        for path in sorted(source.rglob('*')):
            relative = path.relative_to(source)
            if any(part.startswith('.') or part == 'node_modules' for part in relative.parts):
                continue
            if path.is_file() and path.suffix in {'.js', '.html', '.css', '.png', '.svg'}:
                bundle.write(path, 'extension/'+path.relative_to(source).as_posix())
        bundle.write(source/'manifest.json', 'extension/manifest.json')


if __name__ == '__main__':
    package_extension(Path(sys.argv[1]), Path(sys.argv[2]))
