"""
cloudinary_service.py
---------------------
Thin service layer around the Cloudinary Python SDK.

All Cloudinary credentials are read exclusively from environment variables:
    CLOUDINARY_CLOUD_NAME
    CLOUDINARY_API_KEY
    CLOUDINARY_API_SECRET

If any of these are absent the module is considered "unconfigured" and
every public function returns a safe no-op result, allowing the application
to run without Cloudinary in local development.

IMPORTANT:
- The API_SECRET is never passed to templates, logged, or returned in
  any client-facing response.
- Public IDs are generated server-side with uuid4() to prevent client-
  supplied path traversal or arbitrary asset deletion.
"""

import io
import os
import uuid
import logging

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Allowed upload configuration
# ---------------------------------------------------------------------------
ALLOWED_EXTENSIONS = {'jpg', 'jpeg', 'png', 'webp'}
MAX_UPLOAD_BYTES = 5 * 1024 * 1024   # 5 MB
CLOUDINARY_FOLDER = 'trailmate/treks'


def _is_configured():
    """Return True only when all three Cloudinary credentials are present."""
    return bool(
        os.environ.get('CLOUDINARY_CLOUD_NAME') and
        os.environ.get('CLOUDINARY_API_KEY') and
        os.environ.get('CLOUDINARY_API_SECRET')
    )


def _configure():
    """Configure the Cloudinary SDK from environment variables (lazy, cached)."""
    import cloudinary
    cloudinary.config(
        cloud_name=os.environ.get('CLOUDINARY_CLOUD_NAME'),
        api_key=os.environ.get('CLOUDINARY_API_KEY'),
        api_secret=os.environ.get('CLOUDINARY_API_SECRET'),
        secure=True,
    )


def is_cloudinary_configured():
    """Public helper so templates / routes can query capability without SDK import."""
    return _is_configured()


def allowed_file(filename):
    """Return True if the filename has an accepted image extension."""
    if not filename or '.' not in filename:
        return False
    ext = filename.rsplit('.', 1)[-1].lower()
    return ext in ALLOWED_EXTENSIONS


def validate_upload(file_storage):
    """
    Validate a Werkzeug FileStorage object before upload.

    Returns (ok: bool, error_message: str | None)
    """
    if not file_storage or not file_storage.filename:
        return False, 'No file selected.'

    if not allowed_file(file_storage.filename):
        return False, (
            'Unsupported file type. Please upload a JPEG, PNG, or WebP image.'
        )

    # Read the file into memory to check its size; rewind afterwards
    data = file_storage.read()
    file_storage.stream = io.BytesIO(data)  # rewind for later upload

    if not data:
        return False, 'The uploaded file is empty.'

    if len(data) > MAX_UPLOAD_BYTES:
        size_mb = len(data) / (1024 * 1024)
        return False, (
            f'File is too large ({size_mb:.1f} MB). Maximum allowed size is 5 MB.'
        )

    return True, None


def upload_trek_image(file_storage):
    """
    Upload a trek image to Cloudinary.

    Parameters
    ----------
    file_storage : werkzeug.datastructures.FileStorage

    Returns
    -------
    dict with keys:
        'url'        (str)  – the secure HTTPS delivery URL
        'public_id'  (str)  – the Cloudinary public ID for later management
    or raises RuntimeError on failure.
    """
    if not _is_configured():
        raise RuntimeError(
            'Cloudinary is not configured. '
            'Set CLOUDINARY_CLOUD_NAME, CLOUDINARY_API_KEY, and '
            'CLOUDINARY_API_SECRET environment variables.'
        )

    _configure()
    import cloudinary.uploader

    # Server-generated public ID prevents path traversal / client-controlled names
    public_id = f'{CLOUDINARY_FOLDER}/{uuid.uuid4().hex}'

    try:
        result = cloudinary.uploader.upload(
            file_storage.stream,
            public_id=public_id,
            overwrite=True,
            resource_type='image',
            format='jpg',        # normalise to JPEG for consistent delivery
            quality='auto',
            fetch_format='auto',
        )
    except Exception as exc:
        logger.error('Cloudinary upload failed: %s', exc)
        raise RuntimeError(f'Image upload failed: {exc}') from exc

    return {
        'url': result['secure_url'],
        'public_id': result['public_id'],
    }


def delete_trek_image(public_id):
    """
    Delete an asset from Cloudinary by its server-recorded public ID.

    This function must NEVER accept client-supplied public IDs.
    Only call it with a public_id read from the database.

    Parameters
    ----------
    public_id : str  – the Cloudinary public ID stored in Trek.image_public_id

    Returns
    -------
    True on success (or if Cloudinary is not configured), False on error.
    """
    if not public_id:
        return True

    if not _is_configured():
        logger.warning('Cloudinary not configured; skipping asset deletion for %s', public_id)
        return False

    # Safety check: only delete assets inside our designated folder prefix
    if not public_id.startswith(CLOUDINARY_FOLDER + '/'):
        logger.error(
            'Refusing to delete Cloudinary asset with unexpected public_id: %s', public_id
        )
        return False

    _configure()
    import cloudinary.uploader

    try:
        result = cloudinary.uploader.destroy(public_id, resource_type='image')
        if result.get('result') not in ('ok', 'not found'):
            logger.warning('Cloudinary deletion returned unexpected result: %s', result)
            return False
        return True
    except Exception as exc:
        logger.error('Cloudinary deletion failed for %s: %s', public_id, exc)
        return False
