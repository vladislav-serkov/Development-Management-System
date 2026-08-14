"""Export service: pack a project's `.context/` layout into an in-memory zip."""
import io
import zipfile


def create_project_zip(files: dict[str, bytes]) -> bytes:
    """Zip ``{relative_path: bytes}`` (as produced by ``dump_project``) under a
    `.context/` root."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for rel_path, content in files.items():
            zf.writestr(f".context/{rel_path}", content)
    buf.seek(0)
    return buf.read()
