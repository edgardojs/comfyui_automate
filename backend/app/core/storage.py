"""File storage utility for sprite character projects.

Manages the directory structure for character profiles, reference images,
training datasets, LoRA outputs, and preview images. All directories are
auto-created on first access.

The storage root is configurable via the ``SPRITE_PROJECTS_DIR`` environment
variable (default: ``./sprite_projects``).

Directory layout::

    sprite_projects/
    └── {project_name}/
        └── {character_name}/
            ├── references/    — uploaded reference images
            ├── dataset/       — curated + captioned training images
            ├── loras/         — trained LoRA output files
            └── previews/      — preview images generated with the LoRA
"""

import os
import shutil
import uuid
from pathlib import Path

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

SPRITE_PROJECTS_DIR = os.environ.get(
    "SPRITE_PROJECTS_DIR", str(Path(__file__).resolve().parent.parent / "sprite_projects")
)

ALLOWED_IMAGE_EXTENSIONS: set[str] = {".png", ".jpg", ".jpeg", ".webp"}

# Maximum number of files allowed in a single upload request
MAX_UPLOAD_FILES = 20

# Maximum size per uploaded file (10 MB)
MAX_FILE_SIZE = 10 * 1024 * 1024

# Magic bytes (file signatures) for allowed image types
_IMAGE_SIGNATURES: dict[str, list[bytes]] = {
    ".png": [b"\x89PNG\r\n\x1a\n"],
    ".jpg": [b"\xff\xd8\xff"],
    ".jpeg": [b"\xff\xd8\xff"],
    ".webp": [b"RIFF"],  # WebP starts with RIFF, then WEBP at offset 8
}


def validate_image_content(file_content: bytes, extension: str) -> bool:
    """Validate that file content matches the claimed image extension.

    Checks the magic bytes (file signature) at the beginning of the file
    to confirm the content type matches the extension. This prevents
    malicious files disguised with a different extension.

    Args:
        file_content: Raw bytes of the file.
        extension: The claimed file extension (e.g., '.png').

    Returns:
        True if the content matches the extension, False otherwise.
    """
    ext = extension.lower()
    if ext not in _IMAGE_SIGNATURES:
        return False

    signatures = _IMAGE_SIGNATURES[ext]
    for sig in signatures:
        if file_content[: len(sig)] == sig:
            # For WebP, also check the "WEBP" marker at offset 8
            if ext == ".webp" and len(file_content) >= 12:
                return file_content[8:12] == b"WEBP"
            return True

    return False

# ---------------------------------------------------------------------------
# Directory helpers
# ---------------------------------------------------------------------------


def get_project_dir(project_name: str) -> Path:
    """Return the path to a project directory, creating it if needed.

    Args:
        project_name: Sanitized project name (used as folder name).

    Returns:
        Absolute path to ``{SPRITE_PROJECTS_DIR}/{project_name}/``.
    """
    path = Path(SPRITE_PROJECTS_DIR) / _sanitize(project_name)
    path.mkdir(parents=True, exist_ok=True)
    return path.resolve()


def get_character_dir(project_name: str, character_name: str) -> Path:
    """Return the path to a character directory, creating it if needed.

    Args:
        project_name: Sanitized project name.
        character_name: Sanitized character name.

    Returns:
        Absolute path to ``{project}/{character}/``.
    """
    path = get_project_dir(project_name) / _sanitize(character_name)
    path.mkdir(parents=True, exist_ok=True)
    return path


def get_references_dir(project_name: str, character_name: str) -> Path:
    """Return the path to a character's references directory.

    Creates the directory if it does not exist.
    """
    path = get_character_dir(project_name, character_name) / "references"
    path.mkdir(parents=True, exist_ok=True)
    return path


def get_dataset_dir(project_name: str, character_name: str) -> Path:
    """Return the path to a character's dataset directory.

    Creates the directory if it does not exist.
    """
    path = get_character_dir(project_name, character_name) / "dataset"
    path.mkdir(parents=True, exist_ok=True)
    return path


def get_lora_dir(project_name: str, character_name: str) -> Path:
    """Return the path to a character's LoRA output directory.

    Creates the directory if it does not exist.
    """
    path = get_character_dir(project_name, character_name) / "loras"
    path.mkdir(parents=True, exist_ok=True)
    return path


def get_previews_dir(project_name: str, character_name: str) -> Path:
    """Return the path to a character's previews directory.

    Creates the directory if it does not exist.
    """
    path = get_character_dir(project_name, character_name) / "previews"
    path.mkdir(parents=True, exist_ok=True)
    return path


# ---------------------------------------------------------------------------
# File operations
# ---------------------------------------------------------------------------


def save_reference_image(
    character_id: str,
    file_content: bytes,
    original_filename: str,
    project_name: str,
    character_name: str,
) -> Path:
    """Save an uploaded reference image to the character's references directory.

    The file is stored with a unique prefix to avoid name collisions while
    preserving the original extension.

    Args:
        character_id: The character profile ID (used for logging only).
        file_content: Raw bytes of the uploaded image.
        original_filename: Original filename from the upload (used for extension).
        project_name: Project name for directory resolution.
        character_name: Character name for directory resolution.

    Returns:
        Absolute path to the saved file.

    Raises:
        ValueError: If the file extension is not an allowed image type.
    """
    ext = Path(original_filename).suffix.lower()
    if ext not in ALLOWED_IMAGE_EXTENSIONS:
        raise ValueError(
            f"Unsupported image extension '{ext}'. "
            f"Allowed: {', '.join(sorted(ALLOWED_IMAGE_EXTENSIONS))}"
        )

    # Validate file content matches the claimed extension (defense-in-depth)
    if not validate_image_content(file_content, ext):
        raise ValueError(
            f"File content does not match the claimed extension '{ext}'. "
            "The file may be corrupted or disguised."
        )

    # Sanitize the filename to prevent path traversal attacks:
    # 1. Replace backslashes with forward slashes (handles Windows-style paths)
    # 2. Extract only the basename (strips any directory components like ../)
    safe_filename = Path(original_filename.replace("\\", "/")).name
    ref_dir = get_references_dir(project_name, character_name)
    unique_name = f"{uuid.uuid4().hex[:8]}_{safe_filename}"
    dest = ref_dir / unique_name

    # Verify the resolved path is still within the references directory
    # (prevents any remaining path traversal via symlinks or edge cases)
    if not str(dest.resolve()).startswith(str(ref_dir.resolve())):
        raise ValueError(
            f"Invalid filename '{original_filename}': resolved path escapes "
            f"the references directory."
        )

    dest.write_bytes(file_content)
    return dest.resolve()


def delete_character_files(project_name: str, character_name: str) -> None:
    """Delete an entire character directory tree.

    Removes the character folder and all contents (references, dataset,
    loras, previews).

    Args:
        project_name: Project name for directory resolution.
        character_name: Character name for directory resolution.
    """
    char_dir = get_character_dir(project_name, character_name)
    if char_dir.exists():
        shutil.rmtree(char_dir)


def delete_reference_image(file_path: str) -> None:
    """Delete a single reference image file from disk.

    Validates that the file path is within the expected project directory
    before deleting, to prevent path traversal attacks.

    Args:
        file_path: Absolute or relative path to the file.

    Raises:
        ValueError: If the resolved path is outside the project directory.
    """
    path = Path(file_path).resolve()
    project_root = Path(SPRITE_PROJECTS_DIR).resolve()
    if not path.is_relative_to(project_root):
        raise ValueError(
            f"Refusing to delete file outside project directory: {file_path}"
        )
    if path.exists():
        path.unlink()


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _sanitize(name: str) -> str:
    """Sanitize a project or character name for use as a directory name.

    Strips leading/trailing whitespace, replaces spaces with underscores,
    and removes characters that are unsafe for filesystem paths.

    Leading dots are stripped to prevent creation of hidden directories
    (e.g., a project named ``.hidden`` would create a ``.hidden/`` directory).
    """
    sanitized = name.strip().replace(" ", "_")
    # Remove any character that isn't alphanumeric, underscore, hyphen, or dot
    sanitized = "".join(c for c in sanitized if c.isalnum() or c in ("_", "-", "."))
    # Strip leading dots to prevent hidden directories
    sanitized = sanitized.lstrip(".")
    return sanitized or "unnamed"