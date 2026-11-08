"""
Validators for the passport-size photo upload on Student.photo.

Enforces (per the Admission Pro photo-upload spec):
  - File type: JPEG / JPG / PNG only
  - Max file size: 2 MB
  - Minimum resolution + a passport-style (portrait, roughly square-to-tall)
    aspect ratio, so people can't upload a landscape scan or a tiny thumbnail
    as their "passport photo".
"""
from django.core.exceptions import ValidationError
from django.template.defaultfilters import filesizeformat

# Tunable constants - kept at module level so they're easy to adjust without
# hunting through validator logic, and so forms/templates can reference the
# same numbers in help text.
MAX_PHOTO_SIZE_MB = 2
MAX_PHOTO_SIZE_BYTES = MAX_PHOTO_SIZE_MB * 1024 * 1024

ALLOWED_PHOTO_CONTENT_TYPES = {'image/jpeg', 'image/png'}
ALLOWED_PHOTO_EXTENSIONS = {'jpg', 'jpeg', 'png'}

# Passport photos are conventionally portrait, close to a 35mm x 45mm
# (ratio ~0.78) or 2in x 2in (ratio 1.0) format. We accept a tolerance band
# rather than one exact ratio since phone crops vary, but reject anything
# clearly landscape or absurdly thin/tall.
MIN_PHOTO_ASPECT_RATIO = 0.7   # width / height
MAX_PHOTO_ASPECT_RATIO = 1.05  # width / height
MIN_PHOTO_DIMENSION_PX = 200   # minimum width AND height, in pixels


def validate_photo(file):
    """
    Validate an uploaded passport-size photo for type, size, and dimensions.

    Raises django.core.exceptions.ValidationError with a user-facing message
    on the first failing check. Safe to use as a model field validator and
    inside a form's clean_photo().
    """
    # 1. File size
    if file.size > MAX_PHOTO_SIZE_BYTES:
        raise ValidationError(
            f"Photo is too large ({filesizeformat(file.size)}). "
            f"Maximum allowed size is {MAX_PHOTO_SIZE_MB}MB."
        )

    # 2. Extension (cheap first check)
    name = getattr(file, 'name', '') or ''
    ext = name.rsplit('.', 1)[-1].lower() if '.' in name else ''
    if ext not in ALLOWED_PHOTO_EXTENSIONS:
        raise ValidationError(
            "Unsupported file type. Only JPEG, JPG, or PNG images are allowed for the passport photo."
        )

    # 3. Content-type (extension can be spoofed, so check what was actually
    #    uploaded too, when the upload handler provides it).
    content_type = getattr(file, 'content_type', None)
    if content_type and content_type not in ALLOWED_PHOTO_CONTENT_TYPES:
        raise ValidationError(
            "Unsupported file type. Only JPEG, JPG, or PNG images are allowed for the passport photo."
        )

    # 4. Dimensions / aspect ratio - open the image with Pillow. This also
    #    acts as a sanity check that the file really is a readable image.
    try:
        from PIL import Image
        file.seek(0)
        with Image.open(file) as img:
            width, height = img.size
    except Exception:
        raise ValidationError("Could not read this image file. Please upload a valid JPEG or PNG photo.")
    finally:
        try:
            file.seek(0)
        except Exception:
            pass

    if width < MIN_PHOTO_DIMENSION_PX or height < MIN_PHOTO_DIMENSION_PX:
        raise ValidationError(
            f"Photo resolution is too low ({width}x{height}px). "
            f"Please upload an image at least {MIN_PHOTO_DIMENSION_PX}x{MIN_PHOTO_DIMENSION_PX}px."
        )

    aspect_ratio = width / height
    if not (MIN_PHOTO_ASPECT_RATIO <= aspect_ratio <= MAX_PHOTO_ASPECT_RATIO):
        raise ValidationError(
            "Photo does not look like a passport-size photo. "
            "Please upload a portrait photo close to a square (e.g. 35mm x 45mm or 2in x 2in), "
            "not a wide/landscape image."
        )
